"""The task state machine. Every legal edge is here; everything else is a bug."""

from __future__ import annotations

from works.domain.errors import StateError
from works.domain.records import TaskState

S = TaskState

ALLOWED: dict[TaskState, frozenset[TaskState]] = {
    S.QUEUED: frozenset({S.REPRODUCING, S.BLOCKED}),
    S.REPRODUCING: frozenset({S.REPRODUCED, S.BLOCKED}),
    S.REPRODUCED: frozenset({S.PLANNING, S.BLOCKED}),
    S.PLANNING: frozenset({S.PLAN_APPROVED, S.BLOCKED}),
    S.PLAN_APPROVED: frozenset({S.BUILDING, S.BLOCKED}),
    S.BUILDING: frozenset({S.CHECKING, S.BLOCKED}),
    S.CHECKING: frozenset({S.PROVED, S.BLOCKED, S.BUILDING}),
    S.PROVED: frozenset({S.RELEASING, S.WAITING_REVIEW, S.BLOCKED}),
    S.WAITING_REVIEW: frozenset({S.RELEASING, S.BLOCKED}),
    S.RELEASING: frozenset({S.RELEASED, S.WAITING_CI, S.BLOCKED}),
    S.WAITING_CI: frozenset({S.WAITING_DEPLOY, S.RELEASED, S.BLOCKED}),
    S.WAITING_DEPLOY: frozenset({S.RELEASED, S.WAITING_REVIEW, S.BLOCKED}),
    S.RELEASED: frozenset({S.REVERTED, S.QUEUED}),
    S.BLOCKED: frozenset(),
    S.REVERTED: frozenset(),
}

TERMINAL = frozenset({S.BLOCKED, S.REVERTED})
WAITING = frozenset({S.WAITING_REVIEW, S.WAITING_CI, S.WAITING_DEPLOY})


def can_transition(current: TaskState, target: TaskState) -> bool:
    return target in ALLOWED[current]


def require_transition(current: TaskState, target: TaskState) -> None:
    if not can_transition(current, target):
        raise StateError(
            f"cannot move {current.value} -> {target.value}; "
            f"allowed: {sorted(s.value for s in ALLOWED[current])}"
        )
