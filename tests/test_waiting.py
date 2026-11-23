from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from works.adapters.queue.store import Queue
from works.config import WorksPaths
from works.domain.errors import StateError
from works.domain.records import Source, SourceKind, TaskState


def to_proved(queue: Queue, task_id: str) -> None:
    for target in (
        TaskState.REPRODUCING,
        TaskState.REPRODUCED,
        TaskState.PLANNING,
        TaskState.PLAN_APPROVED,
        TaskState.BUILDING,
        TaskState.CHECKING,
        TaskState.PROVED,
    ):
        queue.transition(task_id, target)


def make(paths: WorksPaths) -> tuple[Queue, str]:
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="GH-1"),
        flow="fix-issue",
        product="openjiuwen",
        repo=".",
    )
    to_proved(queue, task.id)
    return queue, task.id


def test_wait_and_wake_round_trip(paths: WorksPaths) -> None:
    queue, task_id = make(paths)
    queue.wait(
        task_id,
        on="review",
        wake_on="review_approved",
        next_state=TaskState.RELEASING,
    )
    waiting = queue.load(task_id)
    assert waiting.state is TaskState.WAITING_REVIEW
    assert waiting.waiting_on == "review"
    assert waiting.wake_on == "review_approved"
    assert waiting.wake_next is TaskState.RELEASING

    queue.wake(task_id, "review_approved")
    assert queue.load(task_id).state is TaskState.RELEASING
    assert queue.load(task_id).wake_on is None
    queue.verify_projection(task_id)


def test_a_wrong_event_does_not_wake_the_task(paths: WorksPaths) -> None:
    queue, task_id = make(paths)
    queue.transition(task_id, TaskState.RELEASING)
    queue.wait(
        task_id,
        on="ci",
        wake_on="ci_passed",
        next_state=TaskState.WAITING_DEPLOY,
    )
    with pytest.raises(StateError, match="ci_passed"):
        queue.wake(task_id, "ci_failed")
    assert queue.load(task_id).state is TaskState.WAITING_CI


def test_a_deadline_expires_to_the_default(paths: WorksPaths) -> None:
    queue, task_id = make(paths)
    queue.transition(task_id, TaskState.RELEASING)
    queue.wait(
        task_id,
        on="ci",
        wake_on="ci_passed",
        next_state=TaskState.WAITING_DEPLOY,
        deadline=datetime.now(tz=UTC) - timedelta(minutes=1),
        default=TaskState.BLOCKED,
    )
    event = queue.expire_wait(task_id)
    assert event is not None
    assert queue.load(task_id).state is TaskState.BLOCKED


def test_a_deadline_in_the_future_does_not_expire(paths: WorksPaths) -> None:
    queue, task_id = make(paths)
    queue.wait(
        task_id,
        on="review",
        wake_on="approved",
        next_state=TaskState.RELEASING,
        deadline=datetime.now(tz=UTC) + timedelta(hours=1),
    )
    assert queue.expire_wait(task_id) is None
    assert queue.load(task_id).state is TaskState.WAITING_REVIEW
