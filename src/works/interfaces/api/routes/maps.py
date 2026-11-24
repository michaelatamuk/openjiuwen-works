"""Product and detector maps for the queue sidebar."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from works.interfaces.api import read
from works.interfaces.api.wiring import AppState

router = APIRouter()


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.works
    return state


@router.get("/products")
def products(request: Request) -> dict[str, Any]:
    _, payload = read.products(_state(request).paths)
    return payload


@router.get("/detectors")
def detectors(request: Request, refresh: str = "0") -> dict[str, Any]:
    _, payload = read.detectors(
        _state(request).paths, refresh=refresh.lower() in ("1", "true", "yes")
    )
    return payload
