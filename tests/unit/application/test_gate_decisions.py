from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from works.adapters.queue.store import Queue
from works.application.approvals.gates import (
    approval_expired,
    decide_plan,
    expires_at,
)
from works.domain.errors import ConfigError
from works.domain.records import Event, Source, SourceKind, TaskState


def _planning_task(paths, repo, ref: str = "GATE-1"):
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref=ref, title="gate test"),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(repo.path),
    )
    for state in (TaskState.REPRODUCING, TaskState.REPRODUCED, TaskState.PLANNING):
        queue.transition(task.id, state)
    queue.append(
        task.id,
        "plan.drafted",
        {
            "plan_id": f"p-{task.id}-v1",
            "hash": "a" * 64,
            "version": 1,
            "base_commit": "b" * 40,
            "checks_sha": "c" * 64,
        },
    )
    return task.id


def test_a_person_approves_and_the_event_is_complete(paths, repo) -> None:
    task_id = _planning_task(paths, repo)

    task, event = decide_plan(paths, task_id, by="michael", device="laptop", comment="good plan")

    assert task.state is TaskState.PLAN_APPROVED
    assert event.type == "gate.decided"
    for key in (
        "by",
        "device",
        "actor_kind",
        "comment",
        "plan_id",
        "plan_hash",
        "commit",
        "checks_sha",
        "expires_at",
    ):
        assert key in event.data
    assert event.data["by"] == "michael"


def test_an_agent_cannot_approve(paths, repo) -> None:
    task_id = _planning_task(paths, repo)

    with pytest.raises(ConfigError, match="agent cannot"):
        decide_plan(paths, task_id, by="builder")

    with pytest.raises(ConfigError, match="agent cannot"):
        decide_plan(paths, task_id, by="michael", actor_kind="agent")


def test_requesting_changes_needs_a_comment_and_keeps_planning(paths, repo) -> None:
    task_id = _planning_task(paths, repo)

    with pytest.raises(ConfigError, match="needs a comment"):
        decide_plan(paths, task_id, decision="changes_requested")

    task, event = decide_plan(
        paths,
        task_id,
        decision="changes_requested",
        comment="name the failing test",
        by="michael",
    )

    assert task.state is TaskState.PLANNING
    assert event.data["decision"] == "changes_requested"
    assert event.data["comment"] == "name the failing test"


def test_rejecting_needs_a_reason_and_blocks(paths, repo) -> None:
    task_id = _planning_task(paths, repo)

    with pytest.raises(ConfigError, match="needs a comment"):
        decide_plan(paths, task_id, decision="rejected")

    task, event = decide_plan(
        paths, task_id, decision="rejected", comment="wrong approach", by="michael"
    )

    assert task.state is TaskState.BLOCKED
    assert event.data["decision"] == "rejected"


def test_a_stale_plan_hash_is_refused(paths, repo) -> None:
    task_id = _planning_task(paths, repo)

    with pytest.raises(ConfigError, match="does not match"):
        decide_plan(paths, task_id, plan_hash="d" * 64, by="michael")


def test_quorum_needs_a_second_person(paths, repo, monkeypatch) -> None:
    monkeypatch.setenv("WORKS_REQUIRE_QUORUM", "1")
    task_id = _planning_task(paths, repo)

    task, pending = decide_plan(paths, task_id, by="michael", device="laptop")
    assert task.state is TaskState.PLANNING
    assert pending.type == "gate.approval"

    task, event = decide_plan(paths, task_id, by="michael", device="phone")
    assert task.state is TaskState.PLAN_APPROVED
    assert event.data["quorum"] is True


def test_the_same_person_and_device_cannot_fill_a_quorum(paths, repo, monkeypatch) -> None:
    monkeypatch.setenv("WORKS_REQUIRE_QUORUM", "1")
    task_id = _planning_task(paths, repo)
    decide_plan(paths, task_id, by="michael", device="laptop")

    with pytest.raises(ConfigError, match="same person on the same device"):
        decide_plan(paths, task_id, by="michael", device="laptop")


def test_an_expired_approval_is_detected() -> None:
    past = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat()
    event = Event(seq=1, ts=datetime.now(tz=UTC), type="gate.decided", data={"expires_at": past})

    assert approval_expired(event) is True

    future = Event(
        seq=2,
        ts=datetime.now(tz=UTC),
        type="gate.decided",
        data={"expires_at": expires_at()},
    )
    assert approval_expired(future) is False


def test_a_decision_on_a_non_planning_task_is_refused(paths, repo) -> None:
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="GATE-2", title="queued"),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(repo.path),
    )

    with pytest.raises(ConfigError, match="needs planning"):
        decide_plan(paths, task.id, by="michael")
