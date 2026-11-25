"""Signed webhook intake. Authentication is the HMAC, not the local bearer token."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from works.application import webhooks
from works.interfaces.api.wiring import AppState

router = APIRouter()


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.works
    return state


@router.post("/hooks/{source}")
async def receive(source: str, request: Request) -> JSONResponse:
    body = await request.body()
    headers = {key.lower(): value for key, value in request.headers.items()}
    status, payload = webhooks.handle(_state(request).paths, source, headers, body)
    return JSONResponse(status_code=status, content=payload)
