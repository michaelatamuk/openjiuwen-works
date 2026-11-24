"""Small local metrics surface for scripts and the debug bundle."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from works.adapters.queue.files import INDEX_FILE
from works.adapters.queue.index import TaskIndex
from works.interfaces.api.wiring import AppState

router = APIRouter()


@router.get("/ops/metrics")
def ops_metrics(request: Request) -> dict[str, object]:
    state: AppState = request.app.state.works
    tasks = 0
    index_path = state.paths.queue / INDEX_FILE
    if index_path.is_file():
        try:
            tasks = TaskIndex(index_path).count()
        except sqlite3.DatabaseError:
            tasks = 0
    return {
        "ok": True,
        "jobs": state.jobs.metrics(),
        "sse_clients": state.live.subscriber_count(),
        "tasks": tasks,
    }
