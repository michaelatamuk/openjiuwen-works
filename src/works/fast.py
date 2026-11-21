"""The read path for `status`. Standard library only: no pydantic, no YAML startup cost."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .index import TaskIndex

INDEX_NAME = "index.sqlite3"


def summaries(queue_dir: Path) -> list[dict[str, Any]] | None:
    path = queue_dir / INDEX_NAME
    if not path.exists():
        if not any(queue_dir.glob("*/task.json")):
            return []
        return None
    try:
        return TaskIndex(path).list()
    except sqlite3.DatabaseError:
        return None


def summary(queue_dir: Path, task_id: str) -> dict[str, Any] | None:
    path = queue_dir / INDEX_NAME
    if not path.exists():
        return None
    try:
        return TaskIndex(path).get(task_id)
    except sqlite3.DatabaseError:
        return None


def event_count(queue_dir: Path, task_id: str) -> int:
    path = queue_dir / task_id / "events.jsonl"
    if not path.exists():
        return 0
    try:
        with path.open("rb") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def owner(queue_dir: Path, task_id: str) -> str | None:
    path = queue_dir / task_id / "owner"
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None
