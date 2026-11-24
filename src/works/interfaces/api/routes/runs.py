"""Runs and dispatch as background jobs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from works.domain.errors import NotFoundError, WorksError
from works.domain.records import TaskState
from works.interfaces.api.jobs import JobContext
from works.interfaces.api.security import require_write
from works.interfaces.api.wiring import AppState, build_supervisor

router = APIRouter()


class RunOptions(BaseModel):
    model_config = {"extra": "forbid"}

    approve_plan: bool = False
    scenarios: str | None = None
    quarantine: str | None = None
    trace: str | None = None
    live: bool = False
    swarm: bool = False
    model: str | None = None
    model_base: str | None = None
    prompt: str | None = None
    ppma: str | None = None
    ppma_space: str = "me"
    decision: str | None = None
    verifier: str = "local"
    verifier_image: str | None = None


class RunRequest(RunOptions):
    task_id: str


class DispatchRequest(RunOptions):
    limit: int = Field(default=10, ge=1, le=100)


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.works
    return state


def _resolve(state: AppState, raw: str | None) -> Path | None:
    if not raw:
        return None
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return (state.paths.root / path).resolve()


def _run_one(state: AppState, options: RunOptions, task_id: str) -> dict[str, Any]:
    state.queue.load(task_id)
    supervisor = build_supervisor(
        state.paths,
        task_id=task_id,
        trace=options.trace,
        live=options.live,
        swarm=options.swarm,
        model=options.model,
        model_base=options.model_base,
        prompt=options.prompt,
        ppma=options.ppma,
        ppma_space=options.ppma_space,
        decision=options.decision,
        verifier=options.verifier,
        verifier_image=options.verifier_image,
    )
    record = asyncio.run(
        supervisor.run(
            task_id,
            approve_plan=options.approve_plan,
            scenario_set=_resolve(state, options.scenarios),
            quarantine=_resolve(state, options.quarantine),
        )
    )
    run: dict[str, Any] = record.model_dump(mode="json")
    return run


@router.post("/runs", dependencies=[Depends(require_write)])
def start_run(payload: RunRequest, request: Request) -> JSONResponse:
    state = _state(request)
    state.queue.load(payload.task_id)

    def run(ctx: JobContext) -> dict[str, Any]:
        ctx.check()
        record = _run_one(state, payload, payload.task_id)
        ctx.check()
        return {"run": record}

    job = state.jobs.submit("run", run, task_id=payload.task_id)
    return JSONResponse(
        status_code=202,
        content={"ok": True, "action": "run", "job": job.as_dict()},
    )


@router.post("/dispatch", dependencies=[Depends(require_write)])
def start_dispatch(payload: DispatchRequest, request: Request) -> JSONResponse:
    state = _state(request)

    def run(ctx: JobContext) -> dict[str, Any]:
        ready = [task for task in state.queue.list_tasks() if task.state is TaskState.QUEUED][
            : payload.limit
        ]
        records: list[dict[str, Any]] = []
        for task in ready:
            ctx.check()
            try:
                records.append({"task_id": task.id, "run": _run_one(state, payload, task.id)})
            except WorksError as exc:
                records.append(
                    {"task_id": task.id, "error": {"code": exc.code, "message": str(exc)}}
                )
            except Exception as exc:  # one task failing must not stop the batch
                records.append(
                    {
                        "task_id": task.id,
                        "error": {
                            "code": "internal_error",
                            "message": f"{type(exc).__name__}: {exc}",
                        },
                    }
                )
        return {"selected": len(ready), "runs": records}

    job = state.jobs.submit("dispatch", run)
    return JSONResponse(
        status_code=202,
        content={"ok": True, "action": "dispatch", "job": job.as_dict()},
    )


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request) -> dict[str, Any]:
    state = _state(request)
    path = state.paths.run_dir(run_id) / "run.json"
    if not path.is_file():
        raise NotFoundError(f"run not found: {run_id}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise NotFoundError(f"run record is not an object: {run_id}")
    return {str(key): value for key, value in raw.items()}
