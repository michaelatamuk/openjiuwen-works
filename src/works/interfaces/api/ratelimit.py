"""Small in-process rate limiter for pairing and auth endpoints."""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

Scope = dict[str, Any]
Message = dict[str, Any]
Send = Callable[[Message], Awaitable[None]]


class RateLimiter:
    def __init__(self, *, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, *, now: float | None = None) -> tuple[bool, float]:
        moment = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= moment - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                retry = max(1, int(hits[0] + self.window - moment))
                return False, float(retry)
            hits.append(moment)
            return True, 0.0


class RateLimitMiddleware:
    """Limit `/pair`, `/session` and admin writes per client address."""

    RULES = (
        ("/api/v1/pair", 10.0, 60.0),
        ("/api/v1/session", 20.0, 60.0),
        ("/api/v1/admin/", 30.0, 60.0),
    )

    def __init__(self, app: Any, *, enabled: bool = True) -> None:
        self.app = app
        self.enabled = enabled
        self._limiters = {
            prefix: RateLimiter(limit=int(limit), window=window)
            for prefix, limit, window in self.RULES
        }

    async def __call__(self, scope: Scope, receive: Any, send: Send) -> None:
        if not self.enabled or scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")
        rule = next((prefix for prefix, _, _ in self.RULES if path.startswith(prefix)), None)
        if rule is None:
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        key = str(client[0]) if client else "local"
        allowed, retry = self._limiters[rule].allow(f"{key}:{rule}")
        if allowed:
            await self.app(scope, receive, send)
            return
        await _too_many(send, retry)


async def _too_many(send: Send, retry: float) -> None:
    body = json.dumps(
        {
            "ok": False,
            "error": {"code": "rate_limited", "message": "too many attempts; try again later"},
        }
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"retry-after", str(int(retry)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
