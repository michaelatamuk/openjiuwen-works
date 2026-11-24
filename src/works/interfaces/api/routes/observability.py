"""Factory metrics and the ledger."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from works.interfaces.api import read
from works.interfaces.api.wiring import AppState

router = APIRouter()


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.works
    return state


@router.get("/metrics")
def metrics(request: Request) -> dict[str, Any]:
    _, payload = read.metrics(_state(request).paths)
    return payload


@router.get("/ledger")
def ledger(request: Request) -> dict[str, Any]:
    _, payload = read.ledger(_state(request).paths)
    return payload
