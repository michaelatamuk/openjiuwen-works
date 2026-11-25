"""Event replay and the task projection."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime

import yaml
from pydantic import ValidationError

from works.domain.enums import TaskState
from works.domain.errors import StateError
from works.domain.records import Event, Task
from works.domain.state import WAITING, require_transition


def _apply(task: Task | None, event: Event) -> Task:
    if event.type == "task.created":
        if task is not None:
            raise StateError("a task.created event must be the first and only one")
        payload = event.data.get("task")
        if not isinstance(payload, dict):
            raise StateError("task.created carries no task payload")
        try:
            created = Task.model_validate(payload)
        except ValidationError as exc:
            raise StateError(f"task.created payload is invalid: {exc}") from exc
        return created.model_copy(update={"updated_at": event.ts})

    if task is None:
        raise StateError(f"event {event.type!r} before task.created")

    if event.type == "state.changed":
        target = event.data.get("to")
        source = event.data.get("from")
        if not isinstance(target, str):
            raise StateError(f"unknown target state {target!r}")
        try:
            target_state = TaskState(target)
        except ValueError as exc:
            raise StateError(f"unknown target state {target!r}") from exc
        if source is not None and source != task.state.value:
            raise StateError(f"event says from={source!r} but the task is {task.state.value!r}")
        require_transition(task.state, target_state)
        return task.model_copy(update={"state": target_state, "updated_at": event.ts})

    if event.type in ("attempt.started", "scheduler.failed"):
        return task.model_copy(update={"attempts": task.attempts + 1, "updated_at": event.ts})

    if event.type == "wait.started":
        target = event.data.get("state")
        if not isinstance(target, str):
            raise StateError(f"unknown waiting state {target!r}")
        try:
            target_state = TaskState(target)
        except (TypeError, ValueError) as exc:
            raise StateError(f"unknown waiting state {target!r}") from exc
        require_transition(task.state, target_state)
        deadline_raw = event.data.get("deadline")
        deadline = (
            datetime.fromisoformat(deadline_raw) if isinstance(deadline_raw, str) else deadline_raw
        )
        next_raw = event.data.get("next")
        default_raw = event.data.get("default")
        wake_next = TaskState(next_raw) if isinstance(next_raw, str) else None
        wake_default = TaskState(default_raw) if isinstance(default_raw, str) else None
        return task.model_copy(
            update={
                "state": target_state,
                "updated_at": event.ts,
                "waiting_on": event.data.get("on"),
                "wake_on": event.data.get("wake_on"),
                "wake_deadline": deadline,
                "wake_next": wake_next,
                "wake_default": wake_default,
            }
        )

    if event.type in ("wait.woken", "wait.expired"):
        if task.state not in WAITING:
            raise StateError(f"task is {task.state.value}, not waiting")
        target = event.data.get("to")
        if not isinstance(target, str):
            raise StateError(f"unknown wake target {target!r}")
        try:
            target_state = TaskState(target)
        except (TypeError, ValueError) as exc:
            raise StateError(f"unknown wake target {target!r}") from exc
        require_transition(task.state, target_state)
        return task.model_copy(
            update={
                "state": target_state,
                "updated_at": event.ts,
                "waiting_on": None,
                "wake_on": None,
                "wake_deadline": None,
                "wake_next": None,
                "wake_default": None,
            }
        )

    if event.type == "reproduction.set":
        command = [str(item) for item in event.data.get("command") or []]
        return task.model_copy(
            update={
                "reproduction_command": command,
                "reproduction_source": str(event.data.get("source") or "person"),
                "updated_at": event.ts,
            }
        )

    if event.type in (
        "note",
        "plan.drafted",
        "plan.deviation",
        "gate.decided",
        "gate.approval",
        "step.started",
        "step.finished",
        "finding",
        "challenge.decided",
        "risk.rated",
        "decision.made",
        "decision.shadow",
        "would_block",
        "flake",
        "preview.finished",
        "memory.reported",
        "memory.failed",
        "memory.recalled",
        "memory.recall_failed",
        "readiness.checked",
        "team.verified",
        "delivery.finished",
        "deploy.finished",
        "escape.detected",
        "rework.detected",
        "confirmation.finished",
        "thread.note",
        "thread.agent",
        "thread.commentary",
        "thread.discussion",
        "task.merged",
        "build.started",
        "build.finished",
        "build.retry",
        "scheduler.tick",
        "scheduler.requested",
        "scheduler.claimed",
        "scheduler.skipped",
        "scheduler.paused",
        "scheduler.resumed",
        "scheduler.reclaimed",
        "scheduler.error",
    ):
        return task.model_copy(update={"updated_at": event.ts})

    raise StateError(f"unknown event type {event.type!r}")


def project(events: Sequence[Event]) -> Task:
    """Pure replay. The same events always rebuild the same task."""
    task: Task | None = None
    for event in events:
        task = _apply(task, event)
    if task is None:
        raise StateError("cannot project an empty event list")
    return task


def dump_task(task: Task) -> str:
    return yaml.safe_dump(task.model_dump(mode="json"), sort_keys=False, allow_unicode=True)


def dump_event(event: Event) -> str:
    return json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
