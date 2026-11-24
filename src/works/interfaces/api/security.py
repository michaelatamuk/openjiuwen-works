"""Local write authentication.

Reads are open on loopback; writes need either the persistent bearer token (CLI) or an HttpOnly
session cookie created from a one-time bootstrap token (`works ui`).
"""

from __future__ import annotations

import contextlib
import hmac
import os
import secrets

from fastapi import Request

from works.config.paths import WorksPaths
from works.domain.errors import AuthError, ReadOnlyError

COOKIE_NAME = "works_session"
CREDENTIAL_FILE = "http-token"


class Security:
    def __init__(self, paths: WorksPaths, *, bootstrap_token: str | None = None) -> None:
        self._token_path = paths.state / CREDENTIAL_FILE
        self._token = self._load_or_create()
        self._bootstrap = bootstrap_token or secrets.token_urlsafe(24)
        self._sessions: set[str] = set()

    @property
    def token(self) -> str:
        return self._token

    @property
    def bootstrap_token(self) -> str:
        return self._bootstrap

    def _load_or_create(self) -> str:
        if self._token_path.exists():
            existing = self._token_path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        token = secrets.token_urlsafe(32)
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(token + "\n", encoding="utf-8", newline="\n")
        with contextlib.suppress(OSError):
            os.chmod(self._token_path, 0o600)
        return token

    def start_session(self, token: str) -> str | None:
        """Consume a bootstrap token or the persistent token; return a session id."""
        supplied = token.strip()
        if not supplied:
            return None
        if self._bootstrap and hmac.compare_digest(supplied, self._bootstrap):
            self._bootstrap = ""
        elif not hmac.compare_digest(supplied, self._token):
            return None
        session = secrets.token_urlsafe(32)
        self._sessions.add(session)
        return session

    def is_authenticated(self, request: Request) -> bool:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            supplied = header[7:].strip()
            if supplied and hmac.compare_digest(supplied, self._token):
                return True
        cookie = request.cookies.get(COOKIE_NAME)
        return bool(cookie and cookie in self._sessions)


def require_write(request: Request) -> None:
    state = request.app.state.works
    if not state.writable:
        raise ReadOnlyError("the daemon is read-only; start it with --write")
    if not state.security.is_authenticated(request):
        raise AuthError("a write token is required; open the daemon with its bootstrap URL")
