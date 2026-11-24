"""Watch the workspace and turn disk changes into named live events."""

from __future__ import annotations

import contextlib
import json
import queue as thread_queue
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from works.config.paths import WorksPaths

Listener = Callable[[list["Change"]], None]


@dataclass(frozen=True)
class Change:
    kind: str
    id: str = ""
    task_id: str = ""
    status: str = ""


class LiveState:
    """Watch the workspace on disk and wake every open browser when it changes."""

    def __init__(self, paths: WorksPaths, *, interval: float = 0.6) -> None:
        self._paths = paths
        self._interval = interval
        self._subscribers: set[thread_queue.Queue[dict[str, Any]]] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._signature: dict[str, tuple[int, int]] | None = None
        self._listener: Listener | None = None

    def set_listener(self, listener: Listener) -> None:
        self._listener = listener

    def start(self) -> None:
        if self._thread is not None:
            return
        self._signature = self._snapshot()
        self._thread = threading.Thread(target=self._loop, name="works-ui-events", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        self._thread = None

    def subscribe(self) -> thread_queue.Queue[dict[str, Any]]:
        channel: thread_queue.Queue[dict[str, Any]] = thread_queue.Queue(maxsize=64)
        with self._lock:
            self._subscribers.add(channel)
        return channel

    def unsubscribe(self, channel: thread_queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers.discard(channel)

    def _files(self) -> list[Path]:
        files = [self._paths.ledger, self._paths.root / ".works" / "settings.json"]
        files.extend(self._paths.queue.glob("*/events.jsonl"))
        files.extend(self._paths.queue.glob("*/task.json"))
        files.extend(self._paths.runs.glob("*/*.json"))
        files.extend(self._paths.runs.glob("*/artifacts/*"))
        files.extend(self._paths.state.glob("jobs/*.json"))
        return files

    def _snapshot(self) -> dict[str, tuple[int, int]]:
        parts: dict[str, tuple[int, int]] = {}
        for path in self._files():
            try:
                stat = path.stat()
            except OSError:
                continue
            parts[str(path)] = (stat.st_mtime_ns, stat.st_size)
        return parts

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            signature = self._snapshot()
            if signature == self._signature:
                continue
            previous = self._signature or {}
            changed = {path for path, value in signature.items() if previous.get(path) != value}
            self._signature = signature
            changes = self._changes(changed)
            payload = {"type": "changed", "at": time.time()}
            with self._lock:
                subscribers = list(self._subscribers)
            for channel in subscribers:
                try:
                    channel.put_nowait(payload)
                except thread_queue.Full:
                    continue
            if changes and self._listener is not None:
                with contextlib.suppress(Exception):
                    self._listener(changes)

    def _changes(self, paths: set[str]) -> list[Change]:
        found: dict[tuple[str, str, str], Change] = {}
        for raw in sorted(paths):
            path = Path(raw)
            try:
                parts = path.relative_to(self._paths.root).parts
            except ValueError:
                continue
            if parts[0] == "queue" and len(parts) >= 3:
                change = Change("task", id=parts[1])
            elif parts[0] == "runs" and len(parts) >= 3:
                change = Change("run", id=parts[1], task_id=self._run_task(parts[1]))
            elif parts[0] == "ledger.jsonl":
                change = Change("queue")
            elif parts[:3] == (".works", "state", "jobs") and len(parts) >= 4:
                job_id = Path(parts[3]).stem
                change = Change("job", id=job_id, status=self._job_status(job_id))
            elif parts[:2] == (".works", "settings.json"):
                change = Change("settings")
            else:
                continue
            found[(change.kind, change.id, change.status)] = change
        return list(found.values())

    def _run_task(self, run_id: str) -> str:
        try:
            payload = json.loads(
                (self._paths.run_dir(run_id) / "run.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return ""
        task_id = payload.get("task_id") if isinstance(payload, dict) else None
        return task_id if isinstance(task_id, str) else ""

    def _job_status(self, job_id: str) -> str:
        try:
            payload = json.loads(
                (self._paths.state / "jobs" / f"{job_id}.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return ""
        status = payload.get("status") if isinstance(payload, dict) else None
        return status if isinstance(status, str) else ""


@dataclass(frozen=True)
class SseEvent:
    id: int
    event: str
    data: dict[str, Any]


class EventHub:
    """Map changes to named events, keep a replay ring and fan out to SSE clients."""

    def __init__(self, paths: WorksPaths, *, ring: int = 200) -> None:
        self._state = LiveState(paths)
        self._state.set_listener(self._publish_changes)
        self._lock = threading.Lock()
        self._counter = 0
        self._ring: deque[SseEvent] = deque(maxlen=ring)
        self._subscribers: set[thread_queue.Queue[SseEvent]] = set()
        self.epoch = secrets.token_hex(4)

    @property
    def counter(self) -> int:
        with self._lock:
            return self._counter

    def start(self) -> None:
        self._state.start()

    def stop(self) -> None:
        self._state.stop()

    def publish(self, event: str, data: dict[str, Any]) -> SseEvent:
        with self._lock:
            self._counter += 1
            item = SseEvent(self._counter, event, data)
            self._ring.append(item)
            subscribers = list(self._subscribers)
        for channel in subscribers:
            try:
                channel.put_nowait(item)
            except thread_queue.Full:
                continue
        return item

    def subscribe(self) -> thread_queue.Queue[SseEvent]:
        channel: thread_queue.Queue[SseEvent] = thread_queue.Queue(maxsize=128)
        with self._lock:
            self._subscribers.add(channel)
        return channel

    def unsubscribe(self, channel: thread_queue.Queue[SseEvent]) -> None:
        with self._lock:
            self._subscribers.discard(channel)

    def events_after(self, last_id: int | None) -> tuple[list[SseEvent], bool]:
        """Return missed events, or a gap flag when the ring no longer covers the client."""
        with self._lock:
            if last_id is None:
                return [], False
            if last_id == self._counter:
                return [], False
            if self._ring and self._ring[0].id <= last_id + 1 <= self._ring[-1].id:
                return [item for item in self._ring if item.id > last_id], False
            if last_id + 1 > self._counter:
                return [], False
            return [], True

    def _publish_changes(self, changes: list[Change]) -> None:
        for change in changes:
            if change.kind == "task":
                self.publish("task.changed", {"task_id": change.id})
            elif change.kind == "run":
                self.publish("run.changed", {"task_id": change.task_id, "run_id": change.id})
            elif change.kind == "job":
                self.publish("job.changed", {"job_id": change.id, "status": change.status})
            elif change.kind == "settings":
                self.publish("settings.changed", {})
            else:
                self.publish("queue.changed", {})
