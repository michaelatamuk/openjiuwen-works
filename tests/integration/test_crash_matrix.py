"""Crash matrix: persisted job states and a real killed process must reconcile safely."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from works.adapters.queue.store import Queue
from works.domain.errors import NotFoundError
from works.domain.records import Source, SourceKind
from works.interfaces.api.jobs import JobRunner

RESTART_MESSAGE = "daemon restarted while the job was running"
STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
SHAPES = ("valid", "truncated", "empty", "extra_field", "not_an_object")


def jobs_dir(paths) -> Path:
    directory = paths.state / "jobs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_job(paths, job_id: str, payload: dict[str, object], shape: str) -> Path:
    path = jobs_dir(paths) / f"{job_id}.json"
    if shape == "truncated":
        path.write_text('{"id": "' + job_id + '", "act', encoding="utf-8")
    elif shape == "empty":
        path.write_text("", encoding="utf-8")
    elif shape == "extra_field":
        path.write_text(json.dumps({**payload, "unknown_field": 1}), encoding="utf-8")
    elif shape == "not_an_object":
        path.write_text("[1, 2, 3]", encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def payload(status: str, job_id: str, task_id: str | None = None) -> dict[str, object]:
    return {
        "id": job_id,
        "action": "deliver",
        "task_id": task_id,
        "status": status,
        "created_at": time.time() - 60,
        "started_at": time.time() - 30 if status == "running" else None,
    }


MATRIX = [(f"{status}-{shape}", status, shape) for status in STATUSES for shape in SHAPES]


def observed(paths, job_id: str) -> str | None:
    """Reconcile once in a fresh runner and return the resulting status, if any."""
    runner = JobRunner(paths, Queue(paths))
    try:
        try:
            return runner.get(job_id).status
        except NotFoundError:
            return None
    finally:
        runner.shutdown()


@pytest.mark.parametrize(("name", "status", "shape"), MATRIX, ids=[row[0] for row in MATRIX])
def test_a_persisted_job_reconciles_to_a_known_state(paths, name, status, shape) -> None:
    job_id = "j-crash"
    write_job(paths, job_id, payload(status, job_id), shape)

    runner = JobRunner(paths, Queue(paths))
    try:
        if shape in ("truncated", "empty", "not_an_object", "extra_field"):
            # A corrupt or unknown record is skipped, never half-applied.
            with pytest.raises(NotFoundError):
                runner.get(job_id)
            assert sum(runner.metrics().values()) == 0
        else:
            job = runner.get(job_id)
            assert job.id == job_id
            if status in ("queued", "running"):
                assert job.status == "failed"
                assert job.error == RESTART_MESSAGE
                assert job.finished_at is not None
                assert job.cancelable is False
                on_disk = json.loads((jobs_dir(paths) / f"{job_id}.json").read_text("utf-8"))
                assert on_disk["status"] == "failed"
                assert on_disk["error"] == RESTART_MESSAGE
            else:
                assert job.status == status
        expected = None if shape != "valid" else runner.get(job_id).status
    finally:
        runner.shutdown()

    # A second restart must not change the answer: reconciliation is idempotent.
    assert observed(paths, job_id) == expected


OWNER_CASES = [
    ("stale-queued-owner-released", "queued", True),
    ("stale-running-owner-released", "running", True),
    ("terminal-succeeded-owner-kept", "succeeded", True),
    ("stale-queued-without-owner", "queued", False),
    ("stale-running-without-owner", "running", False),
]


@pytest.mark.parametrize(
    ("name", "status", "with_owner"), OWNER_CASES, ids=[row[0] for row in OWNER_CASES]
)
def test_reconcile_releases_the_task_owner_of_a_stale_job(paths, name, status, with_owner) -> None:
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="OWNER-1", title="Owner"),
        flow="fix-issue",
        product="Fixture",
        repo=".",
    )
    if with_owner:
        queue.claim(task.id, "owner-a")
    job_id = "j-owner"
    write_job(paths, job_id, payload(status, job_id, task.id), "valid")

    runner = JobRunner(paths, Queue(paths))
    try:
        if status in ("queued", "running"):
            assert queue.owner(task.id) is None
        elif with_owner:
            assert queue.owner(task.id) == "owner-a"
    finally:
        runner.shutdown()


SCRIPT_HEAD = """
import os, time
from works.adapters.queue.store import Queue
from works.config.paths import load_paths
from works.interfaces.api.jobs import JobRunner

paths = load_paths()
runner = JobRunner(paths, Queue(paths))
job = runner.submit("crash", lambda _ctx: time.sleep(120))
print(job.id, flush=True)
"""

# Simulates an abrupt exit (no atexit, no finally) on both platforms.
CRASH_EXIT = SCRIPT_HEAD + "\nos._exit(9)\n"
# Stays alive until the test kills it: TerminateProcess on Windows, SIGKILL on POSIX.
CRASH_HOLD = SCRIPT_HEAD + "\nwhile True:\n    time.sleep(1)\n"


def spawn(paths, script: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=str(paths.root),
        env={**os.environ, "WORKS_HOME": str(paths.root)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_for_job(paths, timeout: float = 30.0) -> str:
    deadline = time.monotonic() + timeout
    directory = jobs_dir(paths)
    while time.monotonic() < deadline:
        found = sorted(directory.glob("*.json"))
        if found:
            return found[0].stem
        time.sleep(0.05)
    raise AssertionError("the crashing process never wrote a job")


def assert_recovered(paths, job_id: str) -> None:
    runner = JobRunner(paths, Queue(paths))
    try:
        job = runner.get(job_id)
        assert job.status == "failed"
        assert job.error == RESTART_MESSAGE
        assert job.finished_at is not None
        assert job.cancelable is False
    finally:
        runner.shutdown()


def test_a_process_that_exits_mid_job_is_failed_on_restart(paths) -> None:
    result = subprocess.run(
        [sys.executable, "-c", CRASH_EXIT],
        cwd=str(paths.root),
        env={**os.environ, "WORKS_HOME": str(paths.root)},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 9, result.stderr
    assert_recovered(paths, result.stdout.strip().splitlines()[-1])


def test_an_externally_killed_process_is_failed_on_restart(paths) -> None:
    process = spawn(paths, CRASH_HOLD)
    try:
        job_id = wait_for_job(paths)
        process.kill()  # TerminateProcess on Windows, SIGKILL on POSIX
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
    assert_recovered(paths, job_id)


def test_a_leftover_atomic_write_temp_file_is_ignored(paths) -> None:
    job_id = "j-crash"
    write_job(paths, job_id, payload("running", job_id), "valid")
    temp = jobs_dir(paths) / f"{job_id}.json.tmp"
    temp.write_text('{"id": "half', encoding="utf-8")

    runner = JobRunner(paths, Queue(paths))
    try:
        assert runner.get(job_id).status == "failed"
        assert runner.metrics()["failed"] == 1
        assert temp.exists()
    finally:
        runner.shutdown()
