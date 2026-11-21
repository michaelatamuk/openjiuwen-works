"""Flaky tests are defects. A flake has an owner, an expiry and a written reason."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from .config import WorksPaths
from .records import SCHEMA_VERSION, utcnow


class FlakeStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class Flake(BaseModel):
    schema_version: int = SCHEMA_VERSION
    id: str
    task_id: str
    scenario_id: str
    owner: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    status: FlakeStatus = FlakeStatus.OPEN
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = None


def flake_id(task_id: str, scenario_id: str, now: datetime) -> str:
    digest = hashlib.sha256(f"{task_id}:{scenario_id}:{now.isoformat()}".encode()).hexdigest()
    return f"f-{digest[:12]}"


def store_path(paths: WorksPaths) -> Path:
    return paths.root / "flakes.jsonl"


def add_flake(
    paths: WorksPaths,
    *,
    task_id: str,
    scenario_id: str,
    owner: str,
    reason: str,
    days: int = 14,
    now: datetime | None = None,
) -> Flake:
    moment = now or datetime.now(tz=UTC)
    flake = Flake(
        id=flake_id(task_id, scenario_id, moment),
        task_id=task_id,
        scenario_id=scenario_id,
        owner=owner,
        reason=reason,
        created_at=moment,
        expires_at=moment + timedelta(days=days),
    )
    path = store_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(flake.model_dump_json() + "\n")
    return flake


def load_flakes(paths: WorksPaths) -> list[Flake]:
    path = store_path(paths)
    if not path.exists():
        return []
    flakes: list[Flake] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            flakes.append(Flake.model_validate_json(line))
    return flakes


def active_flakes(paths: WorksPaths, *, now: datetime | None = None) -> list[Flake]:
    moment = now or datetime.now(tz=UTC)
    return [
        flake
        for flake in load_flakes(paths)
        if flake.status is FlakeStatus.OPEN
        and (flake.expires_at is None or flake.expires_at > moment)
    ]
