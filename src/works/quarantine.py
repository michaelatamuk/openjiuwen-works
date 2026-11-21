"""Quarantine lists and scenario sets live outside the repository. Refused if inside."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from .errors import ConfigError


class QuarantineError(ConfigError):
    code = "quarantine_error"


class Quarantine(BaseModel):
    schema_version: int = 1
    paths: list[str] = Field(default_factory=list)


def is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def ensure_outside(path: Path, repo: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if is_inside(resolved, repo):
        raise QuarantineError(f"{label} must live outside the repository ({repo}); got {resolved}")
    return resolved


def load(path: Path, repo: Path) -> Quarantine:
    resolved = ensure_outside(path, repo, label="quarantine list")
    if not resolved.exists():
        raise QuarantineError(f"quarantine list not found: {resolved}")
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QuarantineError(f"{resolved} is not valid JSON: {exc}") from exc
    try:
        return Quarantine.model_validate(raw)
    except ValidationError as exc:
        raise QuarantineError(f"{resolved} is not a quarantine list: {exc}") from exc


def write(path: Path, repo: Path, paths: list[str]) -> Quarantine:
    resolved = ensure_outside(path, repo, label="quarantine list")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = Quarantine(paths=paths)
    resolved.write_text(payload.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    return payload
