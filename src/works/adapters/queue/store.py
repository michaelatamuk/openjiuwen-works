"""Append-only event store. The projection is derived, never edited by hand."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from filelock import FileLock
from pydantic import ValidationError

from works.adapters.queue.atomic import atomic_write as atomic_write
from works.adapters.queue.index import TaskIndex
from works.adapters.queue.projection import (
    _apply,
    project,
)
from works.adapters.queue.projection import (
    dump_event as dump_event,
)
from works.adapters.queue.projection import (
    dump_task as dump_task,
)
from works.config.paths import WorksPaths
from works.domain.errors import ConflictError, NotFoundError, StateError
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
from works.domain.state import WAITING, require_transition

EVENTS_FILE = "events.jsonl"
TASK_FILE = "task.yaml"
TASK_JSON = "task.json"
INDEX_FILE = "index.sqlite3"
OWNER_FILE = "owner"


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
        task_id = make_task_id(source.kind.value, source.ref)
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
            self._write_projection(task)
            return task, True

    def _write_events(self, task_id: str, events: Sequence[Event]) -> None:
        path = self._dir(task_id) / EVENTS_FILE
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for event in events:
                handle.write(event.model_dump_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _write_projection(self, task: Task) -> None:
        payload = task.model_dump(mode="json")
        text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        atomic_write(self._dir(task.id) / TASK_FILE, text)
        atomic_write(
            self._dir(task.id) / TASK_JSON,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
        self._index_task(payload)

    def _index_task(self, payload: dict[str, Any]) -> None:
        index = TaskIndex(self._paths.queue / INDEX_FILE)
        with self._index_lock():
            if not index.path.exists():
                index.replace(self._scan_payloads())
            index.upsert(payload)

    def _scan_payloads(self) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for path in sorted(self._paths.queue.glob(f"*/{TASK_JSON}")):
            try:
                raw: Any = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(raw, dict):
                payloads.append(raw)
        return payloads

    def rebuild_index(self) -> list[dict[str, Any]]:
        index = TaskIndex(self._paths.queue / INDEX_FILE)
        with self._index_lock():
            index.replace(self._scan_payloads())
            return index.list()

    def load(self, task_id: str) -> Task:
        path = self._dir(task_id) / TASK_FILE
        if not path.exists():
            # A crash between events and projection is recoverable: replay and repair.
            events = self.events(task_id)
            task = project(events)
            self._write_projection(task)
            return task
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise StateError(f"{path} is not a task projection")
        try:
            return Task.model_validate(raw)
        except ValidationError as exc:
            raise StateError(f"{path} is not a valid task: {exc}") from exc

    def events(self, task_id: str) -> list[Event]:
        path = self._dir(task_id) / EVENTS_FILE
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
        self,
        task_id: str,
        event_type: str,
        data: dict[str, Any] | None = None,
        ts: datetime | None = None,
    ) -> Event:
        if not self.exists(task_id):
            raise NotFoundError(f"task not found: {task_id}")
        with self._task_lock(task_id):
            events = self.events(task_id)
            current = project(events)
            event = Event(
                schema_version=SCHEMA_VERSION,
                seq=len(events) + 1,
                ts=ts or utcnow(),
                type=event_type,
                data=data or {},
            )
            updated = _apply(current, event)
            with (self._dir(task_id) / EVENTS_FILE).open(
                "a", encoding="utf-8", newline="\n"
            ) as handle:
                handle.write(event.model_dump_json() + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._write_projection(updated)
            return event

    def transition(self, task_id: str, target: TaskState, *, reason: str = "") -> Event:
        current = self.load(task_id)
        return self.append(
            task_id,
            "state.changed",
            {"from": current.state.value, "to": target.value, "reason": reason},
        )

    def verify_projection(self, task_id: str) -> Task:
        """Replay and compare with the stored projection; raise on divergence."""
        replayed = project(self.events(task_id))
        stored = self.load(task_id)
        if replayed != stored:
            raise StateError(f"projection for {task_id} diverges from its events")
        return stored

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
        targets = {
            "review": TaskState.WAITING_REVIEW,
            "ci": TaskState.WAITING_CI,
            "deploy": TaskState.WAITING_DEPLOY,
        }
        target = targets.get(on)
        if target is None:
            raise StateError(f"unknown wait {on!r}; expected review, ci or deploy")
        current = self.load(task_id)
        require_transition(current.state, target)
        require_transition(target, next_state)
        return self.append(
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

    def wake(self, task_id: str, event: str) -> Event:
        current = self.load(task_id)
        if current.state not in WAITING:
            raise StateError(f"task {task_id} is {current.state.value}, not waiting")
        if current.wake_on != event:
            raise StateError(f"task {task_id} waits on {current.wake_on!r}, not {event!r}")
        if current.wake_next is None:
            raise StateError(f"task {task_id} has no wake target")
        return self.append(
            task_id,
            "wait.woken",
            {"event": event, "to": current.wake_next.value},
        )

    def expire_wait(self, task_id: str, *, now: datetime | None = None) -> Event | None:
        current = self.load(task_id)
        if current.state not in WAITING or current.wake_deadline is None:
            return None
        moment = now or utcnow()
        deadline = current.wake_deadline
        if moment < deadline:
            return None
        target = current.wake_default or TaskState.BLOCKED
        return self.append(
            task_id,
            "wait.expired",
            {"to": target.value, "deadline": deadline.isoformat()},
        )

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

    def claim(self, task_id: str, owner: str) -> None:
        """One owner per task, enforced with O_EXCL. Re-claiming as the same owner is a no-op."""
        directory = self._dir(task_id)
        if not self.exists(task_id):
            raise NotFoundError(f"task not found: {task_id}")
        path = directory / OWNER_FILE
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            current = path.read_text(encoding="utf-8").strip()
            if current == owner:
                return
            raise ConflictError(f"task {task_id} is owned by {current or 'unknown'}") from None
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(owner)
            handle.flush()
            os.fsync(handle.fileno())

    def release(self, task_id: str, owner: str) -> None:
        path = self._dir(task_id) / OWNER_FILE
        if path.exists() and path.read_text(encoding="utf-8").strip() == owner:
            path.unlink()

    def owner(self, task_id: str) -> str | None:
        path = self._dir(task_id) / OWNER_FILE
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8").strip() or None

    def iter_events(self, task_id: str) -> Iterator[Event]:
        yield from self.events(task_id)
