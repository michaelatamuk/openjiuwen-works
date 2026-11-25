"""Scheduler endpoints: status, pause/resume and one tick."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from works.application.scheduling.loop import Scheduler
from works.interfaces.api.jobs import JobContext
from works.interfaces.api.routes.runs import RunOptions, run_task
from works.interfaces.api.security import require_write
from works.interfaces.api.wiring import AppState

router = APIRouter()


class PauseRequest(BaseModel):
    model_config = {"extra": "forbid"}

    reason: str = ""


class TickRequest(RunOptions):
    limit: int = Field(default=1, ge=1, le=10)


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.works
    return state


@router.get("/scheduler")
def scheduler_status(request: Request) -> dict[str, object]:
    state = _state(request)
    payload = Scheduler(state.paths).status()
    payload["jobs"] = state.jobs.metrics()
    return payload


@router.post("/scheduler/pause", dependencies=[Depends(require_write)])
def scheduler_pause(payload: PauseRequest, request: Request) -> dict[str, object]:
    scheduler = Scheduler(_state(request).paths)
    scheduler.pause(payload.reason)
    return {"ok": True, "paused": True, "reason": payload.reason}


@router.post("/scheduler/resume", dependencies=[Depends(require_write)])
def scheduler_resume(request: Request) -> dict[str, object]:
    scheduler = Scheduler(_state(request).paths)
    scheduler.resume()
    return {"ok": True, "paused": False}


@router.post("/scheduler/tick", dependencies=[Depends(require_write)])
def scheduler_tick(payload: TickRequest, request: Request) -> JSONResponse:
    state = _state(request)
    options = payload.model_copy(update={"approve_plan": False})

    def run(ctx: JobContext) -> dict[str, object]:
        scheduler = Scheduler(state.paths)

        def execute(task_id: str) -> None:
            ctx.check()
            run_task(state, options, task_id)

        result = scheduler.tick(execute=execute, limit=payload.limit)
        return {
            "status": result.status,
            "claimed": result.claimed,
            "skipped": result.skipped,
            "reclaimed": result.reclaimed,
            "order": result.order,
            "executed": result.executed,
        }

    job = state.jobs.submit("scheduler", run)
    return JSONResponse(
        status_code=202,
        content={"ok": True, "action": "scheduler.tick", "job": job.as_dict()},
    )
