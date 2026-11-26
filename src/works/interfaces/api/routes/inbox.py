"""Signal triage: duplicate groups, merge, mute.

The inbox is deliberately read-model light: tasks are grouped by a normalised title, because a
webhook, a tracker import and a pasted link often describe the same problem with different refs.
Merging records the decision and blocks the duplicate; it never deletes history.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from works.adapters.queue.atomic import atomic_write
from works.adapters.queue.store import Queue
from works.application import webhooks
from works.config.paths import WorksPaths
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


DISMISS_FILE = "inbox-dismissed.json"
REASON = "same title after normalisation"


class DismissRequest(BaseModel):
    model_config = {"extra": "forbid"}

    signature: str


def _dismissed(paths: WorksPaths) -> set[str]:
    path = paths.state / DISMISS_FILE
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    items = raw.get("signatures") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return set()
    return {str(item) for item in items}


def _remember_dismissal(paths: WorksPaths, signature: str) -> None:
    values = _dismissed(paths)
    values.add(signature)
    paths.state.mkdir(parents=True, exist_ok=True)
    atomic_write(
        paths.state / DISMISS_FILE,
        json.dumps({"signatures": sorted(values)[-200:]}, ensure_ascii=False, sort_keys=True),
    )


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
        ordered = sorted(items, key=lambda item: item.created_at)
        signature = hashlib.sha256(
            "|".join(sorted(task.id for task in ordered)).encode("utf-8")
        ).hexdigest()[:16]
        found.append(
            {
                "key": key,
                "signature": signature,
                "reason": REASON,
                "tasks": [
                    {
                        "id": task.id,
                        "state": task.state.value,
                        "title": task.source.title or task.source.ref,
                        "source": f"{task.source.kind.value}:{task.source.ref}",
                        "flow": task.flow,
                        "created_at": task.created_at.isoformat(),
                    }
                    for task in ordered
                ],
            }
        )
    return sorted(found, key=lambda item: item["key"])


@router.get("/inbox")
def inbox(request: Request) -> JSONResponse:
    queue = Queue(_state(request).paths)
    tasks = queue.list_tasks()
    dismissed = _dismissed(_state(request).paths)
    found = [group for group in groups(tasks) if group["signature"] not in dismissed]
    try:
        reminder_hours = float(os.environ.get("WORKS_GATE_REMINDER_HOURS", "24"))
    except ValueError:
        reminder_hours = 24.0
    now = datetime.now(tz=UTC)
    gates: list[dict[str, Any]] = []
    for task in tasks:
        if task.state is not TaskState.PLANNING:
            continue
        drafts = [event for event in queue.events(task.id) if event.type == "plan.drafted"]
        if not drafts:
            continue
        planned = drafts[-1]
        age_hours = max(0.0, (now - planned.ts).total_seconds() / 3600)
        gates.append(
            {
                "task_id": task.id,
                "title": task.source.title or task.source.ref,
                "plan_version": planned.data.get("version"),
                "waiting_since": planned.ts.isoformat(),
                "waiting_hours": round(age_hours, 1),
                "overdue": age_hours >= reminder_hours,
            }
        )
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "duplicates": found,
            "groups": len(found),
            "gates": gates,
            "reminder_hours": reminder_hours,
        },
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


@router.post("/inbox/dismiss", dependencies=[Depends(require_write)])
def dismiss(payload: DismissRequest, request: Request) -> dict[str, object]:
    signature = payload.signature.strip()
    if not signature:
        raise ConfigError("signature is required")
    _remember_dismissal(_state(request).paths, signature)
    return {"ok": True, "signature": signature}


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


@router.post("/tasks/{task_id}/reproduction", dependencies=[Depends(require_write)])
def set_reproduction(task_id: str, request: Request, payload: dict[str, Any]) -> JSONResponse:
    state = _state(request)
    raw = payload.get("command")
    if isinstance(raw, str):
        command = shlex.split(raw, posix=True)
    elif isinstance(raw, list):
        command = [str(item) for item in raw]
    else:
        raise ConfigError("command must be a list of strings or a quoted string")
    if not command or len(command) > 20 or any(len(item) > 200 for item in command):
        raise ConfigError("command must have 1-20 non-empty parts")
    queue = Queue(state.paths)
    with state.write_lock:
        queue.load(task_id)
        queue.append(task_id, "reproduction.set", {"command": command, "source": "person"})
    return JSONResponse(status_code=200, content={"ok": True, "command": command})
