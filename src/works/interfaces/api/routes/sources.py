"""Source intake: GitHub/Jira/detector imports run as jobs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from works.domain.errors import ConfigError
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
    source = str(payload.get("source") or "").strip()
    if source not in SOURCES:
        raise ConfigError(f"unknown source {source!r}; expected github, jira or detector")

    def run(ctx: JobContext) -> dict[str, Any]:
        from works.interfaces.api import write

        ctx.check()
        _, body = write.run_source(state.paths, payload, state.write_lock)
        return body

    job = state.jobs.submit("sources", run)
    return JSONResponse(
        status_code=202,
        content={"ok": True, "action": "sources", "job": job.as_dict()},
    )
