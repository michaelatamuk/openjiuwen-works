"""Job status and cancellation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from works.interfaces.api.security import require_write
from works.interfaces.api.wiring import AppState

router = APIRouter()


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.works
    return state


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict[str, Any]:
    return _state(request).jobs.get(job_id).as_dict()


@router.delete("/jobs/{job_id}", dependencies=[Depends(require_write)])
def cancel_job(job_id: str, request: Request) -> dict[str, Any]:
    return _state(request).jobs.cancel(job_id).as_dict()
