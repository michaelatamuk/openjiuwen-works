"""The harness port. The engine never imports a model client directly."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from works.domain.records import Challenge


class ReviewRequest(BaseModel):
    """A specialist's slice of the same change."""

    area: str
    focus: list[str] = Field(default_factory=list)
    mode: str = "observe"


class ProposalRequest(BaseModel):
    task_id: str
    source_ref: str
    title: str
    worktree: Path
    base_commit: str
    plan: dict[str, Any] = Field(default_factory=dict)
    review: ReviewRequest | None = None


class Proposal(BaseModel):
    patch: str = ""
    applied: bool = False
    touched_paths: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    prompt_name: str | None = None
    prompt_sha256: str | None = None
    model: str = "unknown"
    provider: str = "unknown"
    version: str = "unknown"
    harness: str | None = None
    tokens: int = Field(default=0, ge=0)
    usd: float = Field(default=0.0, ge=0)
    notes: list[str] = Field(default_factory=list)
    stop: str | None = None


@runtime_checkable
class Harness(Protocol):
    name: str
    supports_reviews: bool

    async def propose(self, request: ProposalRequest) -> Proposal: ...

    async def challenge(self, request: ProposalRequest, proposal: Proposal) -> Challenge: ...
