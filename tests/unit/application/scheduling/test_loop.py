from __future__ import annotations

from datetime import UTC, datetime, timedelta

from works.adapters.queue.store import Queue
from works.application.scheduling import lease
from works.application.scheduling.loop import Scheduler
from works.application.scheduling.policy import POLICY_PATH
from works.domain.enums import TaskState
from works.domain.errors import ConfigError
from works.domain.records import Source, SourceKind

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
POLICY = """
enabled: true
allow:
  manual: true
concurrency:
  global: 1
  per_repo: 1
"""


def _write_policy(paths, text: str = POLICY) -> None:
    path = paths.root / POLICY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _task(paths, ref: str = "R") -> str:
    task, _created = Queue(paths).submit(
        source=Source(kind=SourceKind.MANUAL, ref=ref, title="t"),
        flow="fix-issue",
        product="P",
        repo=str(paths.root / "repo"),
    )
    return task.id


def test_a_disabled_scheduler_claims_nothing(paths) -> None:
    _task(paths)

    result = Scheduler(paths, now=lambda: NOW).tick()

    assert result.status == "disabled"
    assert result.claimed == []


def test_a_tick_claims_and_executes_one_task(paths) -> None:
    _write_policy(paths)
    first = _task(paths, "A")
    second = _task(paths, "B")
    seen: list[str] = []

    def execute(task_id: str) -> None:
        seen.append(task_id)
        Queue(paths).transition(task_id, TaskState.REPRODUCING)

    result = Scheduler(paths, now=lambda: NOW).tick(execute=execute)

    assert result.status == "ok"
    assert result.claimed == [first]
    assert seen == [first]
    assert lease.active_leases(paths, NOW) == []
    assert second in result.order
    events = [item for item in Queue(paths).events(first) if item.type == "scheduler.claimed"]
    assert len(events) == 1
    assert events[0].data["owner"].startswith("scheduler:")
    assert events[0].data["trigger"] == "scheduler"
    assert events[0].data["attempt"] == 1


def test_pause_stops_claiming_and_resume_restores_it(paths) -> None:
    _write_policy(paths)
    _task(paths)
    scheduler = Scheduler(paths, now=lambda: NOW)

    scheduler.pause("operator")
    paused = scheduler.tick()
    assert paused.status == "paused"

    scheduler.resume()
    assert scheduler.tick().status == "ok"


def test_a_busy_slot_holds_the_second_task(paths) -> None:
    _write_policy(paths)
    first = _task(paths, "A")
    second = _task(paths, "B")
    lease.claim(paths, first, owner="scheduler:other", ttl_seconds=600, now=NOW)

    result = Scheduler(paths, now=lambda: NOW).tick()

    assert result.status == "ok"
    assert result.claimed == []
    assert result.skipped[second] == "repo_busy"


def test_status_explains_why_a_task_waits(paths) -> None:
    _write_policy(
        paths,
        """
enabled: true
allow:
  manual: false
""",
    )
    task_id = _task(paths)

    payload = Scheduler(paths, now=lambda: NOW).status()

    assert payload["enabled"] is True
    waiting = payload["waiting"]
    assert isinstance(waiting, dict)
    assert waiting[task_id] == "manual_not_allowed"


def test_a_tick_without_a_runner_releases_its_lease(paths) -> None:
    _write_policy(paths)
    task_id = _task(paths)

    result = Scheduler(paths, now=lambda: NOW).tick()

    assert result.claimed == [task_id]
    assert lease.active_leases(paths, NOW) == []


def test_a_second_tick_after_a_run_does_not_reclaim_the_task(paths) -> None:
    _write_policy(paths)
    task_id = _task(paths)
    scheduler = Scheduler(paths, now=lambda: NOW)

    def execute(item: str) -> None:
        Queue(paths).transition(item, TaskState.REPRODUCING)

    scheduler.tick(execute=execute)
    second = scheduler.tick(execute=execute)

    assert task_id not in second.claimed


def test_the_counter_records_reasons(paths) -> None:
    _write_policy(paths)
    task_id = _task(paths)
    Queue(paths).transition(task_id, TaskState.REPRODUCING)
    scheduler = Scheduler(paths, now=lambda: NOW)

    scheduler.tick()
    payload = scheduler.status()

    counters = payload["counters"]
    assert isinstance(counters, dict)
    assert counters.get("not_runnable") == 1


def _approved(paths, task_id: str, *, expires_in_hours: float, plan_hash: str = "h1") -> None:
    queue = Queue(paths)
    for state in (
        TaskState.REPRODUCING,
        TaskState.REPRODUCED,
        TaskState.PLANNING,
        TaskState.PLAN_APPROVED,
    ):
        queue.transition(task_id, state)
    queue.append(task_id, "plan.drafted", {"hash": plan_hash})
    queue.append(
        task_id,
        "gate.decided",
        {
            "gate": "plan",
            "decision": "approved",
            "plan_hash": plan_hash,
            "expires_at": (NOW + timedelta(hours=expires_in_hours)).isoformat(),
        },
    )


def test_an_expired_plan_approval_is_not_claimed(paths) -> None:
    _write_policy(
        paths,
        """
enabled: true
allow:
  manual: true
levels:
  default: L2
""",
    )
    task_id = _task(paths)
    _approved(paths, task_id, expires_in_hours=-1)

    result = Scheduler(paths, now=lambda: NOW).tick()

    assert task_id not in result.claimed
    assert result.skipped[task_id] == "stale_approval"


def test_a_fresh_plan_approval_is_claimed(paths) -> None:
    _write_policy(
        paths,
        """
enabled: true
allow:
  manual: true
levels:
  default: L2
""",
    )
    task_id = _task(paths)
    _approved(paths, task_id, expires_in_hours=4)

    result = Scheduler(paths, now=lambda: NOW).tick()

    assert result.claimed == [task_id]


def test_a_held_tick_keeps_the_lease_for_the_job(paths) -> None:
    _write_policy(paths)
    task_id = _task(paths)

    result = Scheduler(paths, now=lambda: NOW).tick(hold=True)

    assert result.claimed == [task_id]
    assert [item.task_id for item in lease.active_leases(paths, NOW)] == [task_id]


def test_a_failed_execution_consumes_an_attempt(paths) -> None:
    _write_policy(
        paths,
        """
enabled: true
allow:
  manual: true
queue:
  max_attempts: 1
""",
    )
    task_id = _task(paths)

    def execute(_: str) -> None:
        raise ConfigError("the builder is not configured")

    first = Scheduler(paths, now=lambda: NOW).tick(execute=execute)
    assert task_id in first.claimed
    assert Queue(paths).load(task_id).attempts == 1
    types = [event.type for event in Queue(paths).events(task_id)]
    assert "scheduler.failed" in types

    second = Scheduler(paths, now=lambda: NOW).tick(execute=execute)
    assert task_id not in second.claimed
    assert second.skipped[task_id] == "attempts_exhausted"
