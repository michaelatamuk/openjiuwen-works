"""One span per HTTP request; the tracer is a no-op unless `WORKS_OTEL` is set."""

from __future__ import annotations

from typing import Any

from works.application.observability.tracing import span

Message = dict[str, Any]
Scope = dict[str, Any]


class TracingMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method") or "")
        path = str(scope.get("path") or "")
        with span(f"http {method} {path}", method=method, path=path) as current:

            async def send_spanned(message: Message) -> None:
                if message.get("type") == "http.response.start":
                    current.set_attribute("status", int(message.get("status", 0)))
                await send(message)

            await self.app(scope, receive, send_spanned)
