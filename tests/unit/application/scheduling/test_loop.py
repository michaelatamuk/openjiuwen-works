from __future__ import annotations

import json
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


def _task(paths, ref: str = "R", title: str = "t") -> str:
    task, _created = Queue(paths).submit(
        source=Source(kind=SourceKind.MANUAL, ref=ref, title=title),
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
    assert second.skipped[task_id] == "terminal_failure"


def test_a_skip_is_recorded_once_per_reason(paths) -> None:
    _write_policy(paths)
    task_id = _task(paths)
    Queue(paths).transition(task_id, TaskState.REPRODUCING)
    scheduler = Scheduler(paths, now=lambda: NOW)

    scheduler.tick()
    scheduler.tick()

    skipped = [event for event in Queue(paths).events(task_id) if event.type == "scheduler.skipped"]
    assert len(skipped) == 1
    assert skipped[0].data["reason"] == "not_runnable"


def test_a_tick_writes_a_dispatcher_heartbeat(paths) -> None:
    _write_policy(paths)
    Scheduler(paths, now=lambda: NOW).tick()

    payload = json.loads((paths.state / "dispatcher.json").read_text(encoding="utf-8"))
    assert str(payload["owner"]).startswith("scheduler:")


def test_a_transient_failure_is_retried(paths) -> None:
    from works.domain.errors import HarnessError

    _write_policy(
        paths,
        """
enabled: true
allow:
  manual: true
queue:
  max_attempts: 2
""",
    )
    task_id = _task(paths)

    def execute(_: str) -> None:
        raise HarnessError("the harness died")

    first = Scheduler(paths, now=lambda: NOW).tick(execute=execute)
    second = Scheduler(paths, now=lambda: NOW).tick(execute=execute)

    assert task_id in first.claimed
    assert task_id in second.claimed
    failures = [event for event in Queue(paths).events(task_id) if event.type == "scheduler.failed"]
    assert all(event.data["retryable"] is True for event in failures)


def test_shadow_logs_what_a_knn_order_would_pick(paths, monkeypatch) -> None:
    from works.application.scheduling.estimates import Sample

    _write_policy(
        paths,
        """
enabled: true
allow:
  manual: true
order:
  mode: shadow
""",
    )
    plain = _task(paths, "A", "unrelated words")
    titled = _task(paths, "B", "export drops the last column")
    samples = [
        Sample(
            flow="check-change",
            risk="low",
            minutes=5,
            usd=1,
            title="export drops the last column",
        )
        for _ in range(4)
    ]
    monkeypatch.setattr(
        "works.application.scheduling.loop.enriched_samples", lambda _paths: samples
    )

    Scheduler(paths, now=lambda: NOW).tick()

    events = [
        event
        for event in Queue(paths).events(plain) + Queue(paths).events(titled)
        if event.type == "scheduler.shadow"
    ]
    assert len(events) == 1
    assert events[0].data["would"][0] == titled
    assert events[0].data["rule"][0] != events[0].data["would"][0] or plain < titled


def _released(
    paths,
    task_id: str,
    *,
    proof: str = "p1",
    commit: str = "c1",
    expires_in_hours: float = 4,
) -> None:
    queue = Queue(paths)
    for state in (
        TaskState.REPRODUCING,
        TaskState.REPRODUCED,
        TaskState.PLANNING,
        TaskState.PLAN_APPROVED,
        TaskState.BUILDING,
        TaskState.CHECKING,
        TaskState.PROVED,
        TaskState.RELEASING,
        TaskState.RELEASED,
    ):
        queue.transition(task_id, state)
    queue.append(
        task_id,
        "gate.decided",
        {
            "gate": "release",
            "decision": "approved",
            "proof_sha256": proof,
            "commit": commit,
            "expires_at": (NOW + timedelta(hours=expires_in_hours)).isoformat(),
        },
    )


def _evidence(paths, task_id: str, *, proof: str = "p1", commit: str = "c1") -> None:
    run_dir = paths.runs / "r-release"
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": "r-release",
        "task_id": task_id,
        "flow": "fix-issue",
        "product": "P",
        "source": "manual:R",
        "state": "proved",
        "stop_reason": "completed",
        "base_commit": commit,
        "proof_sha256": proof,
    }
    (run_dir / "evidence.json").write_text(json.dumps(payload), encoding="utf-8")


def test_a_released_task_is_claimed_at_l3(paths) -> None:
    _write_policy(
        paths,
        """
enabled: true
allow:
  manual: true
levels:
  default: L3
""",
    )
    task_id = _task(paths)
    _released(paths, task_id)
    _evidence(paths, task_id)

    result = Scheduler(paths, now=lambda: NOW).tick()

    assert result.claimed == [task_id]


def test_a_changed_proof_makes_the_release_stale(paths) -> None:
    _write_policy(
        paths,
        """
enabled: true
allow:
  manual: true
levels:
  default: L3
""",
    )
    task_id = _task(paths)
    _released(paths, task_id, proof="p1")
    _evidence(paths, task_id, proof="p2")

    result = Scheduler(paths, now=lambda: NOW).tick()

    assert task_id not in result.claimed
    assert result.skipped[task_id] == "stale_approval"


def test_a_claim_is_written_to_the_ledger(paths) -> None:
    _write_policy(paths)
    task_id = _task(paths)

    Scheduler(paths, now=lambda: NOW).tick()

    lines = [line for line in paths.ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any("scheduler claim" in line and "p50" in line for line in lines)
    assert task_id in "".join(lines)


def test_a_labelled_tracker_task_is_claimed_at_l1(paths) -> None:
    _write_policy(
        paths,
        """
enabled: true
allow:
  sources: [github]
  labels: ["works:auto"]
""",
    )
    task, _created = Queue(paths).submit(
        source=Source(
            kind=SourceKind.TRACKER,
            ref="GH-9",
            title="the export drops a column",
            channel="github",
            labels=["works:auto"],
        ),
        flow="fix-issue",
        product="P",
        repo=str(paths.root / "repo"),
    )

    result = Scheduler(paths, now=lambda: NOW).tick()

    assert result.claimed == [task.id]


def test_status_reports_estimates_events_and_errors(paths) -> None:
    _write_policy(paths)
    task_id = _task(paths)
    scheduler = Scheduler(paths, now=lambda: NOW)
    scheduler.pause("deploy")
    scheduler.resume()
    scheduler.log_error("boom")
    scheduler.tick()

    payload = scheduler.status()

    assert payload["enabled"] is True
    estimates = payload["estimates"]
    assert isinstance(estimates, list)
    assert any(item["task_id"] == task_id for item in estimates)
    recent = payload["recent"]
    assert isinstance(recent, list)
    kinds = {str(item["kind"]) for item in recent}
    assert "scheduler.error" in kinds
    assert "scheduler.paused" in kinds


def test_a_knn_source_records_a_neighbour_estimate(paths, monkeypatch) -> None:
    from works.application.scheduling.estimates import Sample

    _write_policy(
        paths,
        """
enabled: true
allow:
  manual: true
estimates:
  source: knn
  min_samples: 3
""",
    )
    task_id = _task(paths, "K", "export drops the last column")
    samples = [
        Sample(
            flow="fix-issue",
            risk="medium",
            minutes=8,
            usd=1,
            title="export drops the last column",
        )
        for _ in range(4)
    ]
    monkeypatch.setattr(
        "works.application.scheduling.loop.enriched_samples", lambda _paths: samples
    )

    payload = Scheduler(paths, now=lambda: NOW).status()

    estimates = payload["estimates"]
    assert isinstance(estimates, list)
    found = next(item for item in estimates if item["task_id"] == task_id)
    assert found["source"] == "knn"


def test_two_tasks_in_one_repo_claim_when_the_policy_allows_it(paths) -> None:
    _write_policy(
        paths, POLICY.replace("global: 1", "global: 2").replace("per_repo: 1", "per_repo: 2")
    )
    first = _task(paths, "A")
    second = _task(paths, "B")

    result = Scheduler(paths, now=lambda: NOW).tick()

    assert set(result.claimed) == {first, second}


def test_a_tick_reserves_the_remaining_budget_across_claims(paths) -> None:
    _write_policy(
        paths,
        POLICY.replace("global: 1", "global: 2").replace("per_repo: 1", "per_repo: 2")
        + "budget:\n  daily_usd: 3.0\n  per_run_usd: 5.0\n",
    )
    first = _task(paths, "A")
    second = _task(paths, "B")

    result = Scheduler(paths, now=lambda: NOW).tick()

    assert len(result.claimed) == 1
    assert result.claimed[0] in {first, second}
    other = second if result.claimed[0] == first else first
    assert result.skipped[other] == "budget_exhausted"
