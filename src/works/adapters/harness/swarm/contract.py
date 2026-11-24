"""The works.swarm.v1 request and result models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

CONTRACT = "works.swarm.v1"


class SwarmRequest(BaseModel):
    contract: str = CONTRACT
    task_id: str
    source_ref: str
    title: str
    worktree: str
    base_commit: str
    plan: dict[str, Any] = Field(default_factory=dict)


class SwarmProposal(BaseModel):
    """What the external builder must return. Only `patch` is required."""

    patch: str = ""
    applied: bool = False
    touched_paths: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    model: str = "jiuwenswarm"
    provider: str = "jiuwenswarm"
    tokens: int = Field(default=0, ge=0)
    usd: float = Field(default=0.0, ge=0)
    notes: list[str] = Field(default_factory=list)
    stop: str | None = None


class SwarmChallenge(BaseModel):
    allow: bool
    reason: str = ""
    concerns: list[str] = Field(default_factory=list)
    model: str = "jiuwenswarm"
    provider: str = "jiuwenswarm"
    tokens: int = Field(default=0, ge=0)
    usd: float = Field(default=0.0, ge=0)


@dataclass(frozen=True)
class SwarmDiagnostic:
    ok: bool
    detail: str
    argv: tuple[str, ...] = ()
    exit_code: int | None = None
    output_tail: str = ""
