"""One specialist reviewer's verdict, kept next to the challenge in the proof."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SpecialistReview(BaseModel):
    area: str
    allow: bool
    reason: str = ""
    concerns: list[str] = Field(default_factory=list)
    model: str = "unknown"
    provider: str = "unknown"
    tokens: int = 0
    usd: float = 0.0
    prompt_sha256: str | None = None
