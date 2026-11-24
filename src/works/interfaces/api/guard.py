"""Loopback-only Host and Origin checks as pure ASGI middleware.

Pure ASGI keeps SSE and streamed responses flowing; BaseHTTPMiddleware buffers them.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

from fastapi import Request

Scope = dict[str, Any]
Message = dict[str, Any]
Send = Callable[[Message], Awaitable[None]]
Authorize = Callable[[Request], bool]

OPEN_PATHS = frozenset({"/api/v1/health", "/api/v1/session"})


class LocalOnlyMiddleware:
    def __init__(self, app: Any, *, trusted: frozenset[str]) -> None:
        self.app = app
        self.trusted = trusted

    async def __call__(self, scope: Scope, receive: Any, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        host_header = headers.get(b"host", b"").decode("latin-1")
        hostname = urlsplit(f"//{host_header}").hostname or ""
        if hostname not in self.trusted:
            await _forbidden(send, "host not allowed")
            return
        origin = headers.get(b"origin", b"").decode("latin-1")
        if origin:
            origin_host = urlsplit(origin).hostname or ""
            if origin_host not in self.trusted and origin_host != hostname:
                await _forbidden(send, "origin not allowed")
                return
        await self.app(scope, receive, send)


class ReadAuthMiddleware:
    """When bound off loopback, every API read needs the bearer token or a session cookie."""

    def __init__(self, app: Any, *, require: bool, authorize: Authorize) -> None:
        self.app = app
        self.require = require
        self.authorize = authorize

    async def __call__(self, scope: Scope, receive: Any, send: Send) -> None:
        if not self.require or scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")
        if not path.startswith("/api/v1") or path in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        if self.authorize(request):
            await self.app(scope, receive, send)
            return
        await _unauthorized(send)


async def _unauthorized(send: Send) -> None:
    body = json.dumps(
        {
            "ok": False,
            "error": {
                "code": "auth_error",
                "message": "reads on a remote bind need the bearer token or a session",
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _forbidden(send: Send, message: str) -> None:
    body = json.dumps(
        {"ok": False, "error": {"code": "forbidden", "message": message}},
        ensure_ascii=False,
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
