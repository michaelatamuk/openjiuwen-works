from __future__ import annotations

import io
import json
import tarfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from works.adapters.queue.store import Queue
from works.config.paths import WorksPaths
from works.domain.records import Source, SourceKind
from works.interfaces.cli.main import main


def invoke(paths, *args: str) -> tuple[int, dict]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(["--home", str(paths.root), *args])
    return code, json.loads(out.getvalue().strip().splitlines()[-1])


def test_backup_restores_tasks_runs_and_settings_without_secrets(paths, tmp_path: Path) -> None:
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="BACKUP-1", title="backup"),
        flow="fix-issue",
        product="Fixture",
        repo=".",
    )
    run_dir = paths.runs / "r-backup"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": "r-backup", "task_id": task.id}), encoding="utf-8"
    )
    (paths.root / ".works" / "settings.json").write_text('{"theme": "dark"}\n', encoding="utf-8")

    archive = tmp_path / "home.tar.gz"
    code, body = invoke(paths, "backup", "--out", str(archive), "--json")
    assert code == 0 and body["ok"] is True
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
    assert f"queue/{task.id}/events.jsonl" in names
    assert "runs/r-backup/run.json" in names
    assert ".works/settings.json" in names
    assert not any("http-token" in name or "devices.json" in name for name in names)

    restored = WorksPaths(tmp_path / "restored").ensure()
    code, body = invoke(restored, "restore", "--from", str(archive), "--json")
    assert code == 0 and body["ok"] is True
    assert Queue(restored).load(task.id).source.ref == "BACKUP-1"
    assert (restored.runs / "r-backup" / "run.json").is_file()
    assert (restored.root / ".works" / "settings.json").is_file()


def test_restore_refuses_to_overwrite_without_force(paths, tmp_path: Path) -> None:
    archive = tmp_path / "empty.tar.gz"
    with tarfile.open(archive, "w:gz"):
        pass
    queue = Queue(paths)
    queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="BACKUP-2", title="existing"),
        flow="fix-issue",
        product="Fixture",
        repo=".",
    )
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(
            [
                "--home",
                str(paths.root),
                "restore",
                "--from",
                str(archive),
                "--json",
            ]
        )
    assert code == 6
    assert "force" in out.getvalue() + err.getvalue()


def test_debug_bundle_omits_credentials(paths, tmp_path: Path) -> None:
    (paths.state / "http-token").write_text("super-secret-token", encoding="utf-8")
    bundle = tmp_path / "bundle.tar.gz"
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(
            [
                "--home",
                str(paths.root),
                "doctor",
                "--json",
                "--bundle",
                str(bundle),
            ]
        )
    assert code in (0, 1)
    with tarfile.open(bundle) as tar:
        names = set(tar.getnames())
        payload = b"".join(tar.extractfile(name).read() for name in names if name.endswith(".json"))
    assert "versions.json" in names
    assert "jobs.json" in names
    assert "index.json" in names
    assert "logs/security.log" in names
    assert b"super-secret-token" not in payload


def test_prune_jobs_archives_only_old_terminal_jobs(paths, tmp_path: Path) -> None:
    import time

    jobs = paths.state / "jobs"
    jobs.mkdir(parents=True, exist_ok=True)
    now = time.time()
    payloads = {
        "j-old": {
            "id": "j-old",
            "action": "demo",
            "status": "succeeded",
            "finished_at": now - 172800,
        },
        "j-new": {"id": "j-new", "action": "demo", "status": "failed", "finished_at": now},
        "j-run": {"id": "j-run", "action": "demo", "status": "running", "finished_at": None},
    }
    for job_id, payload in payloads.items():
        (jobs / f"{job_id}.json").write_text(json.dumps(payload), encoding="utf-8")

    code, body = invoke(paths, "prune-jobs", "--days", "1", "--json")
    assert code == 0 and body["removed"] == 1, body
    assert not (jobs / "j-old.json").exists()
    assert (jobs / "j-new.json").exists()
    assert (jobs / "j-run.json").exists()
    archive = (paths.state / "jobs-archive.jsonl").read_text(encoding="utf-8")
    assert "j-old" in archive
