"""Local process control: an authenticated stop for `works daemon stop`."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from works.domain.errors import AuthError, NotFoundError
from works.interfaces.api.security import require_write
from works.interfaces.api.wiring import AppState

router = APIRouter()


class PairStart(BaseModel):
    label: str = "device"


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


@router.post("/admin/pair", dependencies=[Depends(require_write)])
def start_pairing(request: Request, payload: PairStart) -> dict[str, object]:
    state: AppState = request.app.state.works
    return {"ok": True, **state.security.pairing_start(payload.label)}


@router.get("/admin/devices", dependencies=[Depends(require_write)])
def list_devices(request: Request) -> dict[str, object]:
    state: AppState = request.app.state.works
    return {"ok": True, "devices": state.security.devices()}


@router.delete("/admin/devices/{device_id}", dependencies=[Depends(require_write)])
def revoke_device(device_id: str, request: Request) -> dict[str, bool]:
    state: AppState = request.app.state.works
    if not state.security.revoke_device(device_id):
        raise NotFoundError(f"device not found: {device_id}")
    return {"ok": True, "revoked": True}
