"""One owner per task, enforced with an exclusive file."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from works.adapters.queue.files import OWNER_FILE
from works.domain.errors import ConflictError, NotFoundError

if TYPE_CHECKING:
    from works.adapters.queue.store import Queue


def claim(queue: Queue, task_id: str, owner: str) -> None:
    """One owner per task, enforced with O_EXCL. Re-claiming as the same owner is a no-op."""
    directory = queue._dir(task_id)
    if not queue.exists(task_id):
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


def release(queue: Queue, task_id: str, owner: str) -> None:
    path = queue._dir(task_id) / OWNER_FILE
    if path.exists() and path.read_text(encoding="utf-8").strip() == owner:
        path.unlink()


def owner(queue: Queue, task_id: str) -> str | None:
    path = queue._dir(task_id) / OWNER_FILE
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip() or None
