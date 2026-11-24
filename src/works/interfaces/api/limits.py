"""Request-size limits and request identity for the local daemon."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
DEFAULT_MAX_BODY = 4 * 1024 * 1024


class BodyLimitMiddleware:
    """Reject a declared or streamed request body above `max_bytes` with JSON 413."""

    def __init__(self, app: Any, *, max_bytes: int = DEFAULT_MAX_BODY) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("method") not in BODY_METHODS:
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                length = int(declared)
            except ValueError:
                await _reject(send, 400, "invalid_content_length", "invalid Content-Length")
                return
            if length > self.max_bytes:
                await _too_large(send, self.max_bytes)
                return
            await self.app(scope, receive, send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message.get("type") != "http.request":
                await self.app(scope, _empty_receive(message), send)
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                await _too_large(send, self.max_bytes)
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if replayed:
                return {"type": "http.request", "body": b"", "more_body": False}
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)


def _empty_receive(message: Message) -> Receive:
    async def receive() -> Message:
        return message

    return receive


async def _too_large(send: Send, limit: int) -> None:
    await _reject(
        send,
        413,
        "payload_too_large",
        f"request body exceeds {limit} bytes",
    )


async def _reject(send: Send, status: int, code: str, message: str) -> None:
    body = json.dumps(
        {"ok": False, "error": {"code": code, "message": message}}, ensure_ascii=False
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
