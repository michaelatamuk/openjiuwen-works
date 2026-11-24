"""Local process control: an authenticated stop for `works daemon stop`."""

from __future__ import annotations

from fastapi import APIRouter, Request

from works.domain.errors import AuthError
from works.interfaces.api.wiring import AppState

router = APIRouter()


@router.post("/admin/shutdown", include_in_schema=False)
def shutdown(request: Request) -> dict[str, bool]:
    state: AppState = request.app.state.works
    if not state.security.is_authenticated(request):
        raise AuthError("the write token is required to stop the daemon")
    state.stop_event.set()
    return {"ok": True}


@router.post("/admin/rotate-token", include_in_schema=False)
def rotate_token(request: Request) -> dict[str, str | bool]:
    state: AppState = request.app.state.works
    if not state.security.is_authenticated(request):
        raise AuthError("the write token is required to rotate the token")
    token = state.security.rotate()
    return {"ok": True, "token": token}
