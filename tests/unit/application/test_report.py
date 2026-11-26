from __future__ import annotations

from datetime import timedelta

from tests.unit.domain.test_evidence import fixed_evidence
from works.adapters.queue.store import Queue
from works.application.report import build_report
from works.domain.enums import SourceKind, TaskState
from works.domain.evidence import write_evidence
from works.domain.records import RunRecord, Source, StopReason

WORKFLOW = (
    TaskState.REPRODUCING,
    TaskState.REPRODUCED,
    TaskState.PLANNING,
    TaskState.PLAN_APPROVED,
    TaskState.BUILDING,
    TaskState.CHECKING,
    TaskState.PROVED,
    TaskState.RELEASING,
    TaskState.RELEASED,
)


def _released(paths, repo, ref: str, *, hours: float, usd: float, channel: str | None = None):
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.TRACKER, ref=ref, title=ref, channel=channel),
        flow="fix-issue",
        product="P",
        repo=str(repo.path),
    )
    for state in WORKFLOW:
        queue.transition(task.id, state)
    at = task.created_at + timedelta(hours=hours)
    queue.append(task.id, "gate.decided", {"gate": "plan", "decision": "approved"}, ts=at)
    queue.append(task.id, "gate.decided", {"gate": "release", "decision": "approved"}, ts=at)
    run_id = f"r-{ref}"
    run_dir = paths.runs / run_id
    run_dir.mkdir(parents=True)
    write_evidence(
        run_dir,
        fixed_evidence()
        .model_copy(update={"task_id": task.id, "run_id": run_id, "usd": usd, "tokens": 100})
        .bind(),
    )
    record = RunRecord(
        run_id=run_id,
        task_id=task.id,
        flow="fix-issue",
        state=TaskState.RELEASED,
        stop_reason=StopReason.COMPLETED,
        started_at=task.created_at,
        finished_at=at,
    )
    (run_dir / "run.json").write_text(record.model_dump_json(), encoding="utf-8")
    return task, queue


def test_the_report_counts_time_cost_and_gates(paths, repo) -> None:
    first, queue = _released(paths, repo, "GH-1", hours=2, usd=1.0)
    second, queue = _released(paths, repo, "GH-2", hours=4, usd=3.0, channel="cve")
    queue.append(first.id, "reporter.replied", {"reopened": True, "text": "still broken"})
    queue.append(second.id, "escape.detected", {"note": "a regression"})
    now = first.created_at + timedelta(days=1)

    report = build_report(paths, days=30, now=now)

    assert report.tasks == 2
    assert report.released == 2
    assert report.by_state == {"released": 2}
    assert report.time_to_release.samples == 2
    assert report.time_to_release.median_min == 180.0
    assert report.time_to_release.p90_min == 228.0
    assert report.total_usd == 4.0
    assert report.per_released_usd == 2.0
    assert report.gates["plan"]["approved"] == 2
    assert report.gates["release"]["approved"] == 2
    assert report.reopens == 1
    assert report.cve_tasks == 1
    assert report.cve_released == 1
    assert report.escapes == 1
    assert report.runs == 2
    assert report.stop_reasons == {"completed": 2}


def test_the_window_excludes_older_tasks(paths, repo) -> None:
    task, _ = _released(paths, repo, "GH-3", hours=1, usd=0.5)

    report = build_report(paths, days=30, now=task.created_at + timedelta(days=60))

    assert report.tasks == 0
    assert report.time_to_release.samples == 0


def test_a_task_without_a_release_has_no_time(paths, repo) -> None:
    queue = Queue(paths)
    queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="GH-4", title="open"),
        flow="fix-issue",
        product="P",
        repo=str(repo.path),
    )

    report = build_report(paths, days=30)

    assert report.tasks == 1
    assert report.released == 0
    assert report.time_to_release.median_min is None


def test_the_cli_prints_json(paths, repo) -> None:
    from tests.unit.interfaces.cli.test_cli import invoke, payload

    _released(paths, repo, "GH-5", hours=1, usd=0.25)

    result = invoke(paths, "report", "--days", "30", "--json")

    assert result.exit_code == 0, result.stderr
    body = payload(result)
    assert body["tasks"] == 1
    assert body["released"] == 1
    assert body["total_usd"] == 0.25
    assert body["time_to_release"]["median_min"] == 60.0
