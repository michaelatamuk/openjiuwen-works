"""Wait, wake and expiry events over the task state machine."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from works.domain.errors import StateError
from works.domain.records import Event, TaskState, utcnow
from works.domain.state import WAITING, require_transition

if TYPE_CHECKING:
    from works.adapters.queue.store import Queue


def wait(
    queue: Queue,
    task_id: str,
    *,
    on: str,
    wake_on: str,
    next_state: TaskState,
    deadline: datetime | None = None,
    default: TaskState = TaskState.BLOCKED,
) -> Event:
    targets = {
        "review": TaskState.WAITING_REVIEW,
        "ci": TaskState.WAITING_CI,
        "deploy": TaskState.WAITING_DEPLOY,
    }
    target = targets.get(on)
    if target is None:
        raise StateError(f"unknown wait {on!r}; expected review, ci or deploy")
    current = queue.load(task_id)
    require_transition(current.state, target)
    require_transition(target, next_state)
    return queue.append(
        task_id,
        "wait.started",
        {
            "on": on,
            "state": target.value,
            "wake_on": wake_on,
            "deadline": deadline.isoformat() if deadline else None,
            "next": next_state.value,
            "default": default.value,
        },
    )


def wake(queue: Queue, task_id: str, event: str) -> Event:
    current = queue.load(task_id)
    if current.state not in WAITING:
        raise StateError(f"task {task_id} is {current.state.value}, not waiting")
    if current.wake_on != event:
        raise StateError(f"task {task_id} waits on {current.wake_on!r}, not {event!r}")
    if current.wake_next is None:
        raise StateError(f"task {task_id} has no wake target")
    return queue.append(
        task_id,
        "wait.woken",
        {"event": event, "to": current.wake_next.value},
    )


def expire_wait(queue: Queue, task_id: str, *, now: datetime | None = None) -> Event | None:
    current = queue.load(task_id)
    if current.state not in WAITING or current.wake_deadline is None:
        return None
    moment = now or utcnow()
    deadline = current.wake_deadline
    if moment < deadline:
        return None
    target = current.wake_default or TaskState.BLOCKED
    return queue.append(
        task_id,
        "wait.expired",
        {"to": target.value, "deadline": deadline.isoformat()},
    )
