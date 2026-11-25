"""Signal triage: duplicate groups, merge, mute.

The inbox is deliberately read-model light: tasks are grouped by a normalised title, because a
webhook, a tracker import and a pasted link often describe the same problem with different refs.
Merging records the decision and blocks the duplicate; it never deletes history.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from works.adapters.queue.store import Queue
from works.application import webhooks
from works.domain.errors import ConfigError
from works.domain.records import TaskState
from works.domain.state import TERMINAL
from works.interfaces.api.security import require_write
from works.interfaces.api.wiring import AppState

router = APIRouter()
MIN_KEY = 12


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.works
    return state


def normalise(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def groups(tasks: list[Any]) -> list[dict[str, Any]]:
    buckets: dict[str, list[Any]] = {}
    for task in tasks:
        if task.state in TERMINAL:
            continue
        key = normalise(task.source.title or task.source.ref)
        if len(key) < MIN_KEY:
            continue
        buckets.setdefault(key, []).append(task)
    found: list[dict[str, Any]] = []
    for key, items in buckets.items():
        if len(items) < 2:
            continue
        found.append(
            {
                "key": key,
                "tasks": [
                    {
                        "id": task.id,
                        "state": task.state.value,
                        "title": task.source.title or task.source.ref,
                        "source": f"{task.source.kind.value}:{task.source.ref}",
                    }
                    for task in sorted(items, key=lambda item: item.created_at)
                ],
            }
        )
    return sorted(found, key=lambda item: item["key"])


@router.get("/inbox")
def inbox(request: Request) -> JSONResponse:
    tasks = Queue(_state(request).paths).list_tasks()
    found = groups(tasks)
    return JSONResponse(
        status_code=200,
        content={"ok": True, "duplicates": found, "groups": len(found)},
    )


@router.post("/tasks/{task_id}/merge", dependencies=[Depends(require_write)])
def merge(task_id: str, request: Request, payload: dict[str, Any]) -> JSONResponse:
    state = _state(request)
    into = str(payload.get("into") or "").strip()
    if not into:
        raise ConfigError("into is required")
    if into == task_id:
        raise ConfigError("a task cannot be merged into itself")
    queue = Queue(state.paths)
    with state.write_lock:
        task = queue.load(task_id)
        target = queue.load(into)
        if target.state in TERMINAL:
            raise ConfigError(f"cannot merge into {into}: it is {target.state.value}")
        if task.state not in TERMINAL:
            queue.append(task_id, "task.merged", {"into": into})
            queue.transition(task_id, TaskState.BLOCKED)
    return JSONResponse(
        status_code=200,
        content={"ok": True, "merged": task_id, "into": into, "target_state": target.state.value},
    )


@router.post("/inbox/mute", dependencies=[Depends(require_write)])
def mute(request: Request, payload: dict[str, Any]) -> JSONResponse:
    state = _state(request)
    source = str(payload.get("source") or "").strip()
    if not source:
        raise ConfigError("source is required")
    entries = webhooks.load_registry(state.paths)
    config = entries.get(source)
    if config is None:
        raise ConfigError(f"unknown source {source!r}")
    config.enabled = False
    with state.write_lock:
        webhooks.save_registry(state.paths, entries)
    return JSONResponse(status_code=200, content={"ok": True, "source": config.model_dump()})
