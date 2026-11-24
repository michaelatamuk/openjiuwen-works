"""Keep the derived SQLite index in step with the projections."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from works.adapters.queue.files import INDEX_FILE, TASK_JSON
from works.adapters.queue.index import TaskIndex

if TYPE_CHECKING:
    from works.adapters.queue.store import Queue


def index_task(queue: Queue, payload: dict[str, Any]) -> None:
    index = TaskIndex(queue._paths.queue / INDEX_FILE)
    with queue._index_lock():
        if index.needs_rebuild():
            index.replace(scan_payloads(queue))
        index.upsert(payload)


def scan_payloads(queue: Queue) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for path in sorted(queue._paths.queue.glob(f"*/{TASK_JSON}")):
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(raw, dict):
            payloads.append(raw)
    return payloads


def rebuild_index(queue: Queue) -> list[dict[str, Any]]:
    index = TaskIndex(queue._paths.queue / INDEX_FILE)
    with queue._index_lock():
        index.replace(scan_payloads(queue))
        return index.list()
