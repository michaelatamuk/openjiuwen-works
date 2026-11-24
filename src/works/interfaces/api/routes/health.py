"""Health endpoint backed by the existing read presenter."""

from __future__ import annotations

from fastapi import APIRouter, Request

from works.interfaces.api import read
from works.interfaces.api.schemas.health import Health
from works.interfaces.api.wiring import AppState

router = APIRouter()


@router.get("/health", response_model=Health)
def get_health(request: Request) -> Health:
    state: AppState = request.app.state.works
    _, payload = read.health(state.paths, writable=state.writable)
    return Health.model_validate(payload)
