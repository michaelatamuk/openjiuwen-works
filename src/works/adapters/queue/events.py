"""Read and append events, then rewrite the projection."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import ValidationError

from works.adapters.queue import indexing
from works.adapters.queue.atomic import atomic_write
from works.adapters.queue.files import EVENTS_FILE, TASK_FILE, TASK_JSON
from works.adapters.queue.projection import _apply, project
from works.domain.errors import NotFoundError, StateError
from works.domain.records import SCHEMA_VERSION, Event, Task, TaskState, utcnow

if TYPE_CHECKING:
    from works.adapters.queue.store import Queue


def load(queue: Queue, task_id: str) -> Task:
    path = queue._dir(task_id) / TASK_FILE
    if not path.exists():
        # A crash between events and projection is recoverable: replay and repair.
        events = queue.events(task_id)
        task = project(events)
        write_projection(queue, task)
        return task
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise StateError(f"{path} is not a task projection")
    try:
        return Task.model_validate(raw)
    except ValidationError as exc:
        raise StateError(f"{path} is not a valid task: {exc}") from exc


def events(queue: Queue, task_id: str) -> list[Event]:
    path = queue._dir(task_id) / EVENTS_FILE
    if not path.exists():
        raise NotFoundError(f"task not found: {task_id}")
    events: list[Event] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(Event.model_validate_json(line))
        except ValidationError as exc:
            raise StateError(f"{path}:{number} is not a valid event: {exc}") from exc
    return events


def append(
    queue: Queue,
    task_id: str,
    event_type: str,
    data: dict[str, Any] | None = None,
    ts: datetime | None = None,
) -> Event:
    if not queue.exists(task_id):
        raise NotFoundError(f"task not found: {task_id}")
    with queue._task_lock(task_id):
        events = queue.events(task_id)
        current = project(events)
        event = Event(
            schema_version=SCHEMA_VERSION,
            seq=len(events) + 1,
            ts=ts or utcnow(),
            type=event_type,
            data=data or {},
        )
        updated = _apply(current, event)
        with (queue._dir(task_id) / EVENTS_FILE).open(
            "a", encoding="utf-8", newline="\n"
        ) as handle:
            handle.write(event.model_dump_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        write_projection(queue, updated)
        return event


def transition(queue: Queue, task_id: str, target: TaskState, *, reason: str = "") -> Event:
    current = queue.load(task_id)
    return queue.append(
        task_id,
        "state.changed",
        {"from": current.state.value, "to": target.value, "reason": reason},
    )


def verify_projection(queue: Queue, task_id: str) -> Task:
    """Replay and compare with the stored projection; raise on divergence."""
    replayed = project(queue.events(task_id))
    stored = queue.load(task_id)
    if replayed != stored:
        raise StateError(f"projection for {task_id} diverges from its events")
    return stored


def write_projection(queue: Queue, task: Task) -> None:
    payload = task.model_dump(mode="json")
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    atomic_write(queue._dir(task.id) / TASK_FILE, text)
    atomic_write(
        queue._dir(task.id) / TASK_JSON,
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )
    indexing.index_task(queue, payload)
