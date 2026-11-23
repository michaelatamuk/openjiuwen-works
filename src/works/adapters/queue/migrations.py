"""Schema migrations. One function per bump, tested against an old fixture."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from works.domain.errors import StateError
from works.domain.records import SCHEMA_VERSION, Task

LEGACY_STATES: dict[str, str] = {
    "new": "queued",
    "running": "building",
    "done": "released",
    "failed": "blocked",
    "needs_person": "blocked",
}


def migrate_task(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise StateError("a task record must be a mapping")
    data = dict(raw)
    try:
        version = int(data.get("schema_version", 0))
    except (TypeError, ValueError) as exc:
        raise StateError(f"invalid schema_version: {data.get('schema_version')!r}") from exc
    if version > SCHEMA_VERSION:
        raise StateError(f"record schema v{version} is newer than this build (v{SCHEMA_VERSION})")
    if version < 1:
        data["schema_version"] = 1
        data["state"] = LEGACY_STATES.get(str(data.get("state", "queued")), "queued")
        data.setdefault("product", "unknown")
        data.setdefault("flow", "fix-issue")
        data.setdefault("repo", ".")
        data.setdefault("attempts", 0)
        source = data.get("source")
        if isinstance(source, str):
            data["source"] = {"kind": "manual", "ref": source, "title": ""}
        elif isinstance(source, dict):
            data["source"] = {
                "kind": source.get("kind", "manual"),
                "ref": source.get("ref", "legacy"),
                "title": source.get("title", ""),
            }
        elif source is None:
            data["source"] = {"kind": "manual", "ref": "legacy", "title": ""}
    return data


def load_task(raw: Any) -> Task:
    payload = migrate_task(raw)
    try:
        return Task.model_validate(payload)
    except ValidationError as exc:
        raise StateError(f"task record does not match schema v{SCHEMA_VERSION}: {exc}") from exc
