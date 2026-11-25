"""Server-side replay for side-effecting POSTs that carry `Idempotency-Key`."""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from works.adapters.queue.atomic import atomic_write

Scope = dict[str, Any]
Message = dict[str, Any]
Send = Callable[[Message], Awaitable[None]]
Receive = Callable[[], Awaitable[Message]]

TTL_SECONDS = 24 * 60 * 60
EXCLUDED = (
    "/api/v1/pair",
    "/api/v1/session",
    "/api/v1/admin/",
    "/api/v1/ask/",
    "/api/v1/hooks/",
)


class IdempotencyStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save(self, entries: dict[str, dict[str, Any]]) -> None:
        cutoff = time.time() - TTL_SECONDS
        clean = {
            key: value
            for key, value in entries.items()
            if isinstance(value, dict) and float(value.get("created_at") or 0) > cutoff
        }
        atomic_write(
            self.path,
            json.dumps(clean, ensure_ascii=False, separators=(",", ":")) + "\n",
        )

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            return self._load().get(key)

    def put(self, key: str, record: dict[str, Any]) -> None:
        with self._lock:
            entries = self._load()
            entries[key] = record
            if len(entries) > 2000:
                newest = sorted(entries.items(), key=lambda item: item[1].get("created_at", 0))[
                    -2000:
                ]
                entries = dict(newest)
            self._save(entries)


_STORES: dict[str, IdempotencyStore] = {}
_STORES_LOCK = threading.Lock()


def store_for(path: Path) -> IdempotencyStore:
    key = str(path)
    with _STORES_LOCK:
        store = _STORES.get(key)
        if store is None:
            store = IdempotencyStore(path)
            _STORES[key] = store
        return store


class IdempotencyMiddleware:
    def __init__(self, app: Any, *, enabled: bool = True) -> None:
        self.app = app
        self.enabled = enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.enabled or scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")
        if any(path.startswith(prefix) for prefix in EXCLUDED):
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_key = headers.get(b"idempotency-key", b"").decode("latin-1").strip()
        if not raw_key or len(raw_key) > 200:
            await self.app(scope, receive, send)
            return
        app = scope.get("app")
        state = getattr(getattr(app, "state", None), "works", None)
        if state is None:
            await self.app(scope, receive, send)
            return
        body = await _read_body(receive)
        digest = hashlib.sha256(body).hexdigest()
        store = store_for(state.paths.state / "idempotency.json")
        record = store.get(raw_key)
        if record is not None:
            if record.get("path") != path or record.get("digest") != digest:
                await _conflict(send)
                return
            await _replay(send, record)
            return

        captured: dict[str, Any] = {}
        chunks: list[bytes] = []

        async def replay() -> Message:
            return {"type": "http.request", "body": body, "more_body": False}

        async def capture(message: Message) -> None:
            if message.get("type") == "http.response.start":
                captured["status"] = int(message.get("status") or 0)
                captured["headers"] = [
                    (name.decode("latin-1"), value.decode("latin-1"))
                    for name, value in message.get("headers", [])
                    if name.lower() == b"content-type"
                ]
            elif message.get("type") == "http.response.body":
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    captured["body"] = b"".join(chunks)
                    status = int(captured.get("status") or 0)
                    if 200 <= status < 300:
                        store.put(
                            raw_key,
                            {
                                "path": path,
                                "digest": digest,
                                "status": status,
                                "headers": captured.get("headers", []),
                                "body": base64.b64encode(captured.get("body", b"")).decode("ascii"),
                                "created_at": time.time(),
                            },
                        )
            await send(message)

        await self.app(scope, replay, capture)


async def _read_body(receive: Receive) -> bytes:
    body = bytearray()
    while True:
        message = await receive()
        if message.get("type") != "http.request":
            break
        body.extend(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return bytes(body)


async def _conflict(send: Send) -> None:
    body = json.dumps(
        {
            "ok": False,
            "error": {
                "code": "conflict",
                "message": "Idempotency-Key was reused with a different request",
            },
        }
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 409,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _replay(send: Send, record: dict[str, Any]) -> None:
    body = base64.b64decode(str(record.get("body") or ""))
    headers = [
        (str(name).encode("latin-1"), str(value).encode("latin-1"))
        for name, value in (record.get("headers") or [])
    ]
    headers.append((b"x-idempotent-replay", b"true"))
    await send(
        {
            "type": "http.response.start",
            "status": int(record.get("status") or 200),
            "headers": headers,
        }
    )
    await send({"type": "http.response.body", "body": body})
