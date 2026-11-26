from __future__ import annotations

import types

import pytest

from works.adapters.queue.store import Queue
from works.application.scheduling import lease
from works.application.scheduling.loop import Scheduler
from works.domain.records import Source, SourceKind
from works.interfaces.api import scheduler_loop


class FakeJobs:
    def __init__(self) -> None:
        self.body = None
        self.task_id: str | None = None
        self.fail = False

    def submit(self, kind: str, body, task_id: str | None = None):
        if self.fail:
            raise RuntimeError("queue full")
        self.body = body
        self.task_id = task_id
        return object()


def _task(paths) -> str:
    task, _created = Queue(paths).submit(
        source=Source(kind=SourceKind.MANUAL, ref="R", title="t"),
        flow="fix-issue",
        product="P",
        repo=str(paths.root / "repo"),
    )
    return task.id


def _state(paths, jobs: FakeJobs):
    return types.SimpleNamespace(paths=paths, jobs=jobs)


def test_submit_runs_and_releases_the_lease(paths, monkeypatch) -> None:
    task_id = _task(paths)
    scheduler = Scheduler(paths, owner="scheduler:test")
    lease.claim(paths, task_id, owner="scheduler:test", ttl_seconds=600)
    jobs = FakeJobs()
    monkeypatch.setattr(scheduler_loop, "run_task", lambda *_: {"run": "ok"})

    scheduler_loop._submit(_state(paths, jobs), scheduler, task_id)

    assert jobs.task_id == task_id
    assert jobs.body is not None
    assert jobs.body(types.SimpleNamespace(check=lambda: None)) == {"run": "ok"}
    assert lease.read_lease(paths, task_id) is None


def test_a_failed_job_is_recorded_and_released(paths, monkeypatch) -> None:
    task_id = _task(paths)
    scheduler = Scheduler(paths, owner="scheduler:test")
    lease.claim(paths, task_id, owner="scheduler:test", ttl_seconds=600)
    jobs = FakeJobs()

    def boom(*_args):
        raise RuntimeError("builder missing")

    monkeypatch.setattr(scheduler_loop, "run_task", boom)
    scheduler_loop._submit(_state(paths, jobs), scheduler, task_id)

    assert jobs.body is not None
    with pytest.raises(RuntimeError):
        jobs.body(types.SimpleNamespace(check=lambda: None))
    assert lease.read_lease(paths, task_id) is None
    events = [event for event in Queue(paths).events(task_id) if event.type == "scheduler.failed"]
    assert len(events) == 1


def test_a_refused_submission_releases_the_lease(paths) -> None:
    task_id = _task(paths)
    scheduler = Scheduler(paths, owner="scheduler:test")
    lease.claim(paths, task_id, owner="scheduler:test", ttl_seconds=600)
    jobs = FakeJobs()
    jobs.fail = True

    scheduler_loop._submit(_state(paths, jobs), scheduler, task_id)

    assert lease.read_lease(paths, task_id) is None
