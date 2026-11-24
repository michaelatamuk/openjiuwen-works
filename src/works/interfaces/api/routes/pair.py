"""One-time pairing codes exchanged for a device token."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from works.domain.errors import AuthError
from works.interfaces.api.wiring import AppState

router = APIRouter()


class PairRequest(BaseModel):
    code: str
    label: str | None = None


@router.post("/pair")
def pair(request: Request, payload: PairRequest) -> dict[str, object]:
    state: AppState = request.app.state.works
    paired = state.security.pair(payload.code, payload.label)
    if paired is None:
        raise AuthError("pairing code is invalid or expired")
    return {"ok": True, **paired}
