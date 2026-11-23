from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta

from works.cli import main
from works.escapes import append_events, read_report, scan, write_report
from works.gitops import GitRepo, init_repo
from works.queue import Queue
from works.records import LedgerRow, Source, SourceKind, TaskState


def _escaped_repo(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "calc").mkdir()
    core = repo_path / "calc" / "core.py"
    core.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    repo = init_repo(repo_path)
    base = repo.head()
    core.write_text("def add(a, b):\n    return a + b + 0\n", encoding="utf-8")
    release = repo.commit_all("fix add")
    core.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    revert = repo.commit_all(f'Revert "fix add"\n\nThis reverts commit {release}.')
    core.write_text("def add(a, b):\n    return a + b + 1\n", encoding="utf-8")
    hotfix = repo.commit_all("hotfix: keep the add fix")
    return repo, base, release, revert, hotfix


def _row(paths, task_id: str, run_id: str, *, released_at: datetime) -> None:
    from works.ledger import Ledger

    Ledger(paths.ledger).append(
        LedgerRow(
            ts=released_at,
            task_id=task_id,
            run_id=run_id,
            state=TaskState.RELEASED,
            verdict="allow",
        )
    )


def _run(paths, task_id: str, run_id: str, commit: str) -> None:
    run_dir = paths.runs / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "delivery.json").write_text(
        json.dumps(
            {"task_id": task_id, "run_id": run_id, "commit": commit, "pushed": True}
        ),
        encoding="utf-8",
    )
    (run_dir / "evidence.json").write_text(
        json.dumps({"files_changed": ["calc/core.py"]}), encoding="utf-8"
    )


def _task(paths, ref: str, repo_path, kind: SourceKind = SourceKind.MANUAL):
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=kind, ref=ref, title="add subtracts"),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(repo_path),
    )
    return task


def _setup(tmp_path, paths):
    repo, _base, release, revert, hotfix = _escaped_repo(tmp_path)
    task = _task(paths, "GH-1", repo.path)
    released_at = datetime.now(tz=UTC) - timedelta(days=1)
    _row(paths, task.id, "r-escape", released_at=released_at)
    _run(paths, task.id, "r-escape", release)
    return repo, task, released_at, revert, hotfix


def test_scan_finds_a_revert_and_a_hotfix(tmp_path, paths) -> None:
    _repo, task, _released_at, revert, hotfix = _setup(tmp_path, paths)

    report = scan(paths)

    kinds = {item.kind.value for item in report.findings}
    assert kinds == {"revert", "hotfix"}
    by_kind = {item.kind.value: item for item in report.findings}
    assert by_kind["revert"].evidence_commit == revert
    assert by_kind["hotfix"].evidence_commit == hotfix
    assert all(item.task_id == task.id for item in report.findings)


def test_scan_attributes_rework_from_a_repeated_source(tmp_path, paths) -> None:
    repo, task, _released_at, _revert, _hotfix = _setup(tmp_path, paths)
    later = _task(paths, "GH-1", repo.path, kind=SourceKind.DETECTOR)

    report = scan(paths)

    assert [item.task_id for item in report.rework] == [later.id]
    assert report.rework[0].previous_task_id == task.id


def test_report_round_trips_and_events_are_idempotent(tmp_path, paths) -> None:
    repo, task, _released_at, _revert, _hotfix = _setup(tmp_path, paths)
    later = _task(paths, "GH-1", repo.path, kind=SourceKind.DETECTOR)
    report = scan(paths)

    path = write_report(paths, report)
    append_events(paths, report)
    append_events(paths, report)

    assert path.exists()
    assert read_report(paths) is not None
    events = [event for event in Queue(paths).events(task.id) if event.type == "escape.detected"]
    assert len(events) == 2
    rework_events = [
        event for event in Queue(paths).events(later.id) if event.type == "rework.detected"
    ]
    assert len(rework_events) == 1


def test_scan_without_findings_is_empty(tmp_path, paths) -> None:
    repo = GitRepo(tmp_path / "empty")
    repo.path.mkdir()
    (repo.path / "README.md").write_text("hello\n", encoding="utf-8")
    init_repo(repo.path)
    task = _task(paths, "GH-EMPTY", repo.path)
    _row(paths, task.id, "r-empty", released_at=datetime.now(tz=UTC) - timedelta(days=1))
    _run(paths, task.id, "r-empty", repo.head())

    report = scan(paths)

    assert report.escapes == 0
    assert report.rework == []


def test_metrics_include_escape_and_rework_counts(tmp_path, paths) -> None:
    from works.ledger import Ledger
    from works.metrics import collect

    repo, _task_id, _released_at, _revert, _hotfix = _setup(tmp_path, paths)
    _task(paths, "GH-1", repo.path, kind=SourceKind.DETECTOR)
    report = scan(paths)
    write_report(paths, report)

    metrics = collect(Queue(paths), Ledger(paths.ledger), escape_report=report)

    assert metrics.escapes == 2
    assert metrics.rework == 1


def test_the_cli_scans_and_reports_json(tmp_path, paths) -> None:
    _repo, _task_id, _released_at, _revert, _hotfix = _setup(tmp_path, paths)
    out, err = io.StringIO(), io.StringIO()

    with redirect_stdout(out), redirect_stderr(err):
        code = main(["--home", str(paths.root), "escapes", "--json"])

    assert code == 0, err.getvalue()
    body = json.loads(out.getvalue().strip().splitlines()[-1])
    assert body["escapes"]["escapes"] == 2
    assert body["written"] is True
