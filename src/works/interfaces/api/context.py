"""Request identity and access logging without buffering streaming responses."""

from __future__ import annotations

import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any

Scope = dict[str, Any]
Message = dict[str, Any]
Send = Callable[[Message], Awaitable[None]]

LOG = logging.getLogger("works.http")


class RequestContextMiddleware:
    """Add `X-Request-ID`, put it in the request state and log the finished response."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Any, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"x-request-id", b"").decode("latin-1").strip()
        request_id = supplied or secrets.token_hex(8)
        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state["request_id"] = request_id
        method = str(scope.get("method") or "")
        path = str(scope.get("path") or "")
        started = time.monotonic()
        status = 0

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message.get("type") == "http.response.start":
                status = int(message.get("status") or 0)
                headers_out = message.setdefault("headers", [])
                headers_out.append((b"x-request-id", request_id.encode("latin-1")))
            await send(message)
            if message.get("type") == "http.response.body" and not message.get("more_body", False):
                LOG.info(
                    "%s %s %s",
                    method,
                    path,
                    status,
                    extra={
                        "request_id": request_id,
                        "method": method,
                        "path": path,
                        "status": status,
                        "duration_ms": int((time.monotonic() - started) * 1000),
                    },
                )

        await self.app(scope, receive, send_with_id)
