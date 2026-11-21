"""The harness port. The engine never imports a model client directly."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ProposalRequest(BaseModel):
    task_id: str
    source_ref: str
    title: str
    worktree: Path
    base_commit: str


class Proposal(BaseModel):
    patch: str = ""
    model: str = "unknown"
    provider: str = "unknown"
    tokens: int = Field(default=0, ge=0)
    usd: float = Field(default=0.0, ge=0)
    notes: list[str] = Field(default_factory=list)
    stop: str | None = None


@runtime_checkable
class Harness(Protocol):
    name: str

    async def propose(self, request: ProposalRequest) -> Proposal: ...
