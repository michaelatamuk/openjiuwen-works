"""Builder settings for the next job."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from works.application.settings import builder_health, load_builder_settings, save_builder_settings
from works.domain.errors import ConfigError
from works.interfaces.api.security import require_write
from works.interfaces.api.wiring import AppState

router = APIRouter()


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.works
    return state


@router.get("/settings/builder")
def get_settings(request: Request) -> dict[str, Any]:
    state = _state(request)
    settings = None
    try:
        settings = load_builder_settings(state.paths)
    except ConfigError:
        settings = None
    return {"ok": True, "builder": builder_health(state.paths, settings)}


@router.post("/settings/builder", dependencies=[Depends(require_write)])
def save_settings(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    state = _state(request)
    settings = save_builder_settings(state.paths, payload)
    return {"ok": True, "builder": builder_health(state.paths, settings)}
