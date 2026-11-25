"""Append-only event store. The projection is derived, never edited by hand."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from filelock import FileLock
from pydantic import ValidationError

from works.adapters.queue import claims, indexing, waits
from works.adapters.queue import events as event_store
from works.adapters.queue.atomic import atomic_write as atomic_write
from works.adapters.queue.files import (
    EVENTS_FILE as EVENTS_FILE,
)
from works.adapters.queue.files import (
    INDEX_FILE as INDEX_FILE,
)
from works.adapters.queue.files import (
    OWNER_FILE as OWNER_FILE,
)
from works.adapters.queue.files import (
    TASK_FILE as TASK_FILE,
)
from works.adapters.queue.files import (
    TASK_JSON as TASK_JSON,
)
from works.adapters.queue.projection import dump_event as dump_event
from works.adapters.queue.projection import dump_task as dump_task
from works.adapters.queue.projection import project as project
from works.config.paths import WorksPaths
from works.domain.errors import StateError
from works.domain.records import (
    SCHEMA_VERSION,
    Budget,
    Event,
    Scope,
    Source,
    Task,
    TaskKind,
    TaskState,
    utcnow,
)

__all__ = [
    "EVENTS_FILE",
    "INDEX_FILE",
    "OWNER_FILE",
    "TASK_FILE",
    "TASK_JSON",
    "Queue",
    "atomic_write",
    "dump_event",
    "dump_task",
    "make_task_id",
    "project",
]


def make_task_id(kind: str, ref: str) -> str:
    digest = hashlib.sha256(f"{kind}:{ref}".encode()).hexdigest()
    return f"t-{digest[:12]}"


class Queue:
    def __init__(self, paths: WorksPaths) -> None:
        self._paths = paths

    @property
    def paths(self) -> WorksPaths:
        return self._paths

    def _dir(self, task_id: str) -> Path:
        return self._paths.task_dir(task_id)

    def _root_lock(self) -> FileLock:
        return FileLock(str(self._paths.queue / ".queue.lock"), timeout=30)

    def _task_lock(self, task_id: str) -> FileLock:
        return FileLock(str(self._dir(task_id) / ".lock"), timeout=30)

    def _index_lock(self) -> FileLock:
        return FileLock(str(self._paths.queue / ".index.lock"), timeout=30)

    def exists(self, task_id: str) -> bool:
        return (self._dir(task_id) / EVENTS_FILE).exists()

    def submit(
        self,
        *,
        source: Source,
        flow: str,
        product: str,
        repo: str,
        budget: Budget | None = None,
        scope: Scope | None = None,
        task_kind: TaskKind = TaskKind.FIX,
    ) -> tuple[Task, bool]:
        """Return (task, created). A duplicate source returns the existing task."""
        task_id = make_task_id(source.kind.value, source.identity)
        with self._root_lock():
            if self.exists(task_id):
                return self.load(task_id), False
            directory = self._dir(task_id)
            directory.mkdir(parents=True, exist_ok=True)
            now = utcnow()
            task = Task(
                id=task_id,
                flow=flow,
                product=product,
                repo=repo,
                source=source,
                kind=task_kind,
                budget=budget or Budget(),
                scope=scope or Scope(),
                created_at=now,
                updated_at=now,
            )
            event = Event(
                schema_version=SCHEMA_VERSION,
                seq=1,
                ts=now,
                type="task.created",
                data={"task": task.model_dump(mode="json")},
            )
            self._write_events(task_id, [event])
            event_store.write_projection(self, task)
            return task, True

    def _write_events(self, task_id: str, events: Sequence[Event]) -> None:
        path = self._dir(task_id) / EVENTS_FILE
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for event in events:
                handle.write(event.model_dump_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def list_tasks(self) -> list[Task]:
        tasks: list[Task] = []
        if not self._paths.queue.exists():
            return tasks
        for path in sorted(self._paths.queue.glob(f"*/{TASK_FILE}")):
            raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                try:
                    tasks.append(Task.model_validate(raw))
                except ValidationError as exc:
                    raise StateError(f"{path} is not a valid task: {exc}") from exc
        return sorted(tasks, key=lambda item: item.created_at)

    def iter_events(self, task_id: str) -> Iterator[Event]:
        yield from self.events(task_id)

    def load(self, task_id: str) -> Task:
        return event_store.load(self, task_id)

    def events(self, task_id: str) -> list[Event]:
        return event_store.events(self, task_id)

    def append(
        self,
        task_id: str,
        event_type: str,
        data: dict[str, Any] | None = None,
        ts: datetime | None = None,
    ) -> Event:
        return event_store.append(self, task_id, event_type, data, ts)

    def transition(self, task_id: str, target: TaskState, *, reason: str = "") -> Event:
        return event_store.transition(self, task_id, target, reason=reason)

    def verify_projection(self, task_id: str) -> Task:
        return event_store.verify_projection(self, task_id)

    def rebuild_index(self) -> list[dict[str, Any]]:
        return indexing.rebuild_index(self)

    def wait(
        self,
        task_id: str,
        *,
        on: str,
        wake_on: str,
        next_state: TaskState,
        deadline: datetime | None = None,
        default: TaskState = TaskState.BLOCKED,
    ) -> Event:
        return waits.wait(
            self,
            task_id,
            on=on,
            wake_on=wake_on,
            next_state=next_state,
            deadline=deadline,
            default=default,
        )

    def wake(self, task_id: str, event: str) -> Event:
        return waits.wake(self, task_id, event)

    def expire_wait(self, task_id: str, *, now: datetime | None = None) -> Event | None:
        return waits.expire_wait(self, task_id, now=now)

    def claim(self, task_id: str, owner: str) -> None:
        return claims.claim(self, task_id, owner)

    def release(self, task_id: str, owner: str) -> None:
        return claims.release(self, task_id, owner)

    def owner(self, task_id: str) -> str | None:
        return claims.owner(self, task_id)
