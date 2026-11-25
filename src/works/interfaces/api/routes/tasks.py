"""Read routes for tasks and runs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from works.application.scheduling.triggers import request_dispatch
from works.domain.errors import NotFoundError
from works.interfaces.api import read, write
from works.interfaces.api.schemas.tasks import RunList, TaskDetail, TaskList
from works.interfaces.api.security import require_write
from works.interfaces.api.wiring import AppState

router = APIRouter()


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.works
    return state


@router.get("/tasks", response_model=TaskList)
def list_tasks(request: Request, limit: int = Query(default=200, ge=1, le=1000)) -> TaskList:
    _, payload = read.tasks(_state(request).paths, limit=limit)
    return TaskList.model_validate(payload)


LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def _remote(request: Request) -> bool:
    client = request.client
    return client is None or client.host not in LOOPBACK


@router.post("/tasks", dependencies=[Depends(require_write)])
def create_task(request: Request, payload: dict[str, Any]) -> JSONResponse:
    state = _state(request)
    wants_dispatch = bool(payload.pop("dispatch_on_import", False))
    status, body = write.create_task(state.paths, payload, state.write_lock)
    if wants_dispatch:
        task = body.get("task")
        task_id = str(task.get("id") if isinstance(task, dict) else "")
        result = request_dispatch(state.paths, task_id, remote=_remote(request))
        body["scheduler"] = result.as_dict()
    return JSONResponse(status_code=int(status), content=body)


@router.get("/tasks/{task_id}", response_model=TaskDetail)
def task_detail(task_id: str, request: Request) -> TaskDetail:
    try:
        _, payload = read.detail(_state(request).paths, task_id, api_prefix="/api/v1")
    except NotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return TaskDetail.model_validate(payload)


@router.get("/tasks/{task_id}/runs", response_model=RunList)
def task_runs(task_id: str, request: Request) -> RunList:
    _, payload = read.runs(_state(request).paths, task_id)
    return RunList.model_validate(payload)
