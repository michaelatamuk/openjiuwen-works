"""Session bootstrap: exchange a token for an HttpOnly cookie."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from works.domain.errors import AuthError
from works.interfaces.api.security import COOKIE_NAME
from works.interfaces.api.wiring import AppState

router = APIRouter()
SESSION_MAX_AGE = 8 * 60 * 60


class SessionRequest(BaseModel):
    token: str


@router.post("/session")
def create_session(
    request: Request, payload: SessionRequest, response: Response
) -> dict[str, bool]:
    state: AppState = request.app.state.works
    session = state.security.start_session(payload.token)
    if session is None:
        raise AuthError("invalid bootstrap or write token")
    response.set_cookie(
        COOKIE_NAME,
        session,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return {"ok": True}
