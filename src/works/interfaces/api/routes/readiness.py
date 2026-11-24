"""Repository readiness as a background job."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from works.domain.errors import ConfigError
from works.interfaces.api.security import require_write
from works.interfaces.api.wiring import AppState

router = APIRouter()


class ReadinessRequest(BaseModel):
    repo: str | None = None
    task_id: str | None = None


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.works
    return state


def _repo(state: AppState, payload: ReadinessRequest) -> Path:
    if payload.task_id:
        return Path(state.queue.load(payload.task_id).repo)
    raw = str(payload.repo or "").strip()
    if not raw:
        raise ConfigError("repo or task_id is required")
    path = Path(raw).expanduser()
    return (Path.cwd() / path).resolve() if not path.is_absolute() else path.resolve()


@router.post("/readiness", dependencies=[Depends(require_write)])
def start_readiness(payload: ReadinessRequest, request: Request) -> JSONResponse:
    state = _state(request)
    repo = _repo(state, payload)
    if not repo.is_dir():
        raise ConfigError(f"repository does not exist: {repo}")

    def run(ctx: Any) -> dict[str, Any]:
        from works.application.execution.readiness import assess

        ctx.check()
        return assess(repo, run_commands=True).as_dict()

    job = state.jobs.submit("readiness", run, task_id=payload.task_id)
    return JSONResponse(
        status_code=202,
        content={"ok": True, "action": "readiness", "job": job.as_dict()},
    )
