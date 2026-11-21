"""PPMA is the memory product. Works reports finished runs; PPMA owns the living memory.

The north contract is HTTP: register the `works` manifest once, mint an app token, then post one
`works.run_finished` event per run. The event id is derived from the run id, so retries are
idempotent. Memory is a side effect: an unreachable PPMA never turns a proved run into a failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

from . import __version__
from .evidence import Evidence
from .records import RunRecord, Task

Transport = Callable[[str, str, dict[str, Any] | None, dict[str, str]], tuple[int, Any]]
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
APP_ID = "works"
EVENT_TYPE = "works.run_finished"


def ulid_for(seed: str, *, timestamp_ms: int | None = None) -> str:
    """A deterministic, valid ULID for one run: the same run reports the same id twice."""
    digest = hashlib.sha256(seed.encode()).digest()
    if timestamp_ms is None:
        timestamp_ms = int.from_bytes(digest[:6], "big")
    value = ((timestamp_ms & ((1 << 48) - 1)) << 80) | int.from_bytes(digest[6:16], "big")
    chars: list[str] = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


class Memory(Protocol):
    def record(self, *, task: Task, record: RunRecord, evidence: Evidence) -> None: ...


class NullMemory:
    def record(self, *, task: Task, record: RunRecord, evidence: Evidence) -> None:
        return None


def _urllib_transport(
    method: str, url: str, body: dict[str, Any] | None, headers: dict[str, str]
) -> tuple[int, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"PPMA url must be http(s): {url!r}")
    request = urllib.request.Request(  # noqa: S310  # nosec B310
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310  # nosec B310
            payload = response.read()
            return response.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"error": raw.decode("utf-8", errors="replace")}
        return exc.code, parsed


def manifest() -> dict[str, Any]:
    return {
        "app": APP_ID,
        "version": __version__,
        "display_name": "openJiuwen Works",
        "emits": [
            {
                "type": EVENT_TYPE,
                "description": "One finished factory run with its verdict and proof hash.",
                "payload_schema": {
                    "type": "object",
                    "required": ["task_id", "run_id", "state", "stop_reason"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "source": {"type": "string"},
                        "state": {"type": "string"},
                        "stop_reason": {"type": "string"},
                        "verdict": {"type": ["string", "null"]},
                        "tokens": {"type": "integer"},
                        "usd": {"type": "number"},
                        "duration_ms": {"type": "integer"},
                        "base_commit": {"type": ["string", "null"]},
                        "proof_sha256": {"type": "string"},
                    },
                },
                "sensitivity": "general",
            }
        ],
    }


class PpmaMemory:
    """Report a run to a PPMA backend using the v0 north contract."""

    def __init__(
        self,
        base_url: str,
        *,
        space: str = "me",
        owner_token: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._space = space
        self._owner_token = (
            owner_token
            or os.environ.get("WORKS_PPMA_TOKEN")
            or os.environ.get("PPMA_OWNER_TOKEN")
            or "dev"
        )
        self._transport = transport or _urllib_transport
        self._app_token: str | None = None

    def _call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        token: str,
    ) -> tuple[int, Any]:
        return self._transport(
            method,
            f"{self._base}{path}",
            body,
            {"Authorization": f"Bearer {token}"},
        )

    def _register(self) -> None:
        status, payload = self._call(
            "PUT", f"/v0/apps/{APP_ID}/manifest", manifest(), self._owner_token
        )
        if status not in (200, 201):
            raise RuntimeError(f"PPMA refused the works manifest: {status} {payload}")
        status, payload = self._call(
            "POST",
            f"/v0/apps/{APP_ID}/token",
            {"revoke_previous": False},
            self._owner_token,
        )
        if status != 200 or not isinstance(payload, dict) or not payload.get("token"):
            raise RuntimeError(f"PPMA refused an app token: {status} {payload}")
        self._app_token = str(payload["token"])

    def _message(self, task: Task, record: RunRecord, evidence: Evidence) -> dict[str, Any]:
        return {
            "id": ulid_for(record.run_id),
            "kind": "event",
            "type": EVENT_TYPE,
            "space": self._space,
            "source": {"app": APP_ID, "app_version": __version__},
            "occurred_at": record.finished_at.isoformat(),
            "payload": {
                "task_id": task.id,
                "run_id": record.run_id,
                "source": f"{task.source.kind.value}:{task.source.ref}",
                "state": record.state.value,
                "stop_reason": record.stop_reason.value,
                "verdict": "allow"
                if evidence.verdict and evidence.verdict.allow
                else ("block" if evidence.verdict else None),
                "tokens": record.tokens,
                "usd": record.usd,
                "duration_ms": record.duration_ms,
                "base_commit": record.base_commit,
                "proof_sha256": evidence.proof_sha256,
            },
            "resources": [
                {
                    "uri": f"works://runs/{record.run_id}/evidence",
                    "mime_type": "text/markdown",
                    "title": "Proof",
                }
            ],
        }

    def record(self, *, task: Task, record: RunRecord, evidence: Evidence) -> None:
        if self._app_token is None:
            self._register()
        message = self._message(task, record, evidence)
        status, payload = self._call(
            "POST",
            f"/v0/spaces/{self._space}/messages",
            {"messages": [message]},
            self._app_token or "",
        )
        if status in (401, 403):
            # A rotated token is recoverable: mint a new one and retry the same id.
            self._register()
            status, payload = self._call(
                "POST",
                f"/v0/spaces/{self._space}/messages",
                {"messages": [message]},
                self._app_token or "",
            )
        if status not in (200, 202):
            raise RuntimeError(f"PPMA refused the run event: {status} {payload}")
