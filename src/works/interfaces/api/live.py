"""HTTP API presenters and runtime helpers."""

from __future__ import annotations

import queue as thread_queue
import threading
import time
from typing import Any

from works.config.paths import WorksPaths


class LiveState:
    """Watch the workspace on disk and wake every open browser when it changes."""

    def __init__(self, paths: WorksPaths, *, interval: float = 0.6) -> None:
        self._paths = paths
        self._interval = interval
        self._subscribers: set[thread_queue.Queue[dict[str, Any]]] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._signature: tuple[tuple[str, int, int], ...] | None = None

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

    def _snapshot(self) -> tuple[tuple[str, int, int], ...]:
        files = [self._paths.ledger]
        files.extend(self._paths.queue.glob("*/events.jsonl"))
        files.extend(self._paths.queue.glob("*/task.json"))
        files.extend(self._paths.runs.glob("*/*.json"))
        files.extend(self._paths.runs.glob("*/artifacts/*"))
        parts: list[tuple[str, int, int]] = []
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            parts.append((str(path), stat.st_mtime_ns, stat.st_size))
        return tuple(parts)

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            signature = self._snapshot()
            if signature == self._signature:
                continue
            self._signature = signature
            payload = {"type": "changed", "at": time.time()}
            with self._lock:
                subscribers = list(self._subscribers)
            for channel in subscribers:
                try:
                    channel.put_nowait(payload)
                except thread_queue.Full:
                    continue
