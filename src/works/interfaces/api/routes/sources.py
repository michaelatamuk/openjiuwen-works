"""Source intake: GitHub/Jira/detector imports run as jobs."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from works.application.scheduling.triggers import request_dispatch
from works.domain.errors import ConfigError
from works.interfaces.api.clientaddr import is_remote
from works.interfaces.api.jobs import JobContext
from works.interfaces.api.security import require_write
from works.interfaces.api.wiring import AppState

router = APIRouter()
SOURCES = frozenset({"github", "jira", "detector"})


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.works
    return state


@router.post("/sources", dependencies=[Depends(require_write)])
def import_sources(request: Request, payload: dict[str, Any]) -> JSONResponse:
    state = _state(request)
    wants_dispatch = bool(payload.pop("dispatch_on_import", False))
    remote = is_remote(request)
    source = str(payload.get("source") or "").strip()
    if source not in SOURCES:
        raise ConfigError(f"unknown source {source!r}; expected github, jira or detector")

    def run(ctx: JobContext) -> dict[str, Any]:
        from works.interfaces.api import write

        ctx.check()
        _, body = write.run_source(state.paths, payload, state.write_lock)
        if wants_dispatch:
            results = [
                request_dispatch(state.paths, str(task_id), remote=remote).as_dict()
                for task_id in body.get("tasks", [])
            ]
            body["scheduler"] = results
        return body

    job = state.jobs.submit("sources", run)
    return JSONResponse(
        status_code=202,
        content={"ok": True, "action": "sources", "job": job.as_dict()},
    )


@router.get("/sources")
def list_sources(request: Request) -> JSONResponse:
    state = _state(request)
    from works.application import webhooks

    metrics = webhooks.read_metrics(state.paths)
    entries = webhooks.load_registry(state.paths)
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "sources": [
                {
                    **config.model_dump(exclude={"secret_env"}),
                    "secret_env": config.secret_env,
                    "secret_set": bool(os.environ.get(config.secret_env)),
                    "metrics": metrics.get(name, {}),
                }
                for name, config in entries.items()
            ],
        },
    )
