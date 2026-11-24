from __future__ import annotations

import json
import sys
import threading
import time

import pytest

from works.adapters.processes.runner import SubprocessRunner
from works.adapters.queue.store import Queue
from works.domain.errors import ConflictError
from works.domain.records import Source, SourceKind
from works.interfaces.api.jobs import Job, JobRunner

FINAL = {"succeeded", "failed", "cancelled"}


def wait_for(runner: JobRunner, job_id: str, statuses: set[str], timeout: float = 5.0) -> Job:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = runner.get(job_id)
        if job.status in statuses:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} is {runner.get(job_id).status}, expected {statuses}")


def test_a_job_succeeds_and_persists(paths) -> None:
    runner = JobRunner(paths, Queue(paths))
    try:
        job = runner.submit("demo", lambda _ctx: {"value": 42})
        done = wait_for(runner, job.id, FINAL)
        assert done.status == "succeeded"
        assert done.result == {"value": 42}
        payload = json.loads((paths.state / "jobs" / f"{job.id}.json").read_text(encoding="utf-8"))
        assert payload["status"] == "succeeded"
    finally:
        runner.shutdown()


def test_a_job_failure_is_recorded(paths) -> None:
    def fail(_ctx) -> None:
        raise ValueError("boom")

    runner = JobRunner(paths, Queue(paths))
    try:
        job = runner.submit("demo", fail)
        done = wait_for(runner, job.id, FINAL)
        assert done.status == "failed"
        assert done.error is not None and "boom" in done.error
    finally:
        runner.shutdown()


def test_a_running_job_can_be_cancelled(paths) -> None:
    started = threading.Event()

    def slow(ctx) -> None:
        started.set()
        while not ctx.cancelled:
            time.sleep(0.01)
        ctx.check()

    runner = JobRunner(paths, Queue(paths))
    try:
        job = runner.submit("demo", slow)
        assert started.wait(5)
        runner.cancel(job.id)
        done = wait_for(runner, job.id, FINAL)
        assert done.status == "cancelled"
        assert done.cancelable is False
    finally:
        runner.shutdown()


def test_one_job_per_task(paths) -> None:
    release = threading.Event()

    def slow(_ctx) -> str:
        release.wait(5)
        return "done"

    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="JOB-LOCK-1", title="lock"),
        flow="fix-issue",
        product="Fixture",
        repo=".",
    )
    runner = JobRunner(paths, queue)
    try:
        first = runner.submit("demo", slow, task_id=task.id)
        with pytest.raises(ConflictError):
            runner.submit("demo", slow, task_id=task.id)
        release.set()
        assert wait_for(runner, first.id, FINAL).status == "succeeded"
        second = runner.submit("demo", lambda _ctx: "again", task_id=task.id)
        assert wait_for(runner, second.id, FINAL).status == "succeeded"
    finally:
        runner.shutdown()


def test_reconcile_fails_orphans_and_releases_the_owner(paths) -> None:
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="JOB-ORPHAN-1", title="orphan"),
        flow="fix-issue",
        product="Fixture",
        repo=".",
    )
    queue.claim(task.id, "r-orphan")
    job = Job(id="j-orphan", action="run", task_id=task.id, status="running")
    path = paths.state / "jobs" / "j-orphan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(job.as_dict()) + "\n", encoding="utf-8")

    runner = JobRunner(paths, queue)
    try:
        loaded = runner.get("j-orphan")
        assert loaded.status == "failed"
        assert loaded.error is not None and "restarted" in loaded.error
        assert queue.owner(task.id) is None
    finally:
        runner.shutdown()


def test_the_state_directory_exists(paths) -> None:
    assert paths.state.is_dir()


def test_a_job_carries_a_trace_id(paths) -> None:
    runner = JobRunner(paths, Queue(paths))
    try:
        job = runner.submit("demo", lambda _ctx: "ok")
        assert len(job.trace_id) == 16
        assert job.as_dict()["trace_id"] == job.trace_id
    finally:
        runner.shutdown()


def test_a_job_timeout_fails_and_ignores_the_late_result(paths) -> None:
    release = threading.Event()

    def slow(_ctx) -> str:
        release.wait(2)
        return "late"

    runner = JobRunner(paths, Queue(paths))
    try:
        job = runner.submit("demo", slow, timeout_s=0.05)
        done = wait_for(runner, job.id, FINAL)
        assert done.status == "failed"
        assert done.error_code == "timeout"
        assert done.error is not None and "timed out" in done.error
        release.set()
        time.sleep(0.2)
        assert runner.get(job.id).status == "failed"
    finally:
        runner.shutdown()


def test_cancel_kills_a_child_process(paths) -> None:
    def run_child(_ctx) -> object:
        return SubprocessRunner().run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            paths.root,
            timeout_s=30,
        )

    runner = JobRunner(paths, Queue(paths))
    try:
        job = runner.submit("demo", run_child, timeout_s=30)
        wait_for(runner, job.id, {"running"})
        time.sleep(0.2)
        started = time.monotonic()
        runner.cancel(job.id)
        done = wait_for(runner, job.id, FINAL, timeout=10)
        assert done.status == "cancelled"
        assert time.monotonic() - started < 10
    finally:
        runner.shutdown()
