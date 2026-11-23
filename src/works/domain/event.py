"""Append-only event and structured finding records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .base import SCHEMA_VERSION, utcnow


class Event(BaseModel):
    schema_version: int = SCHEMA_VERSION
    seq: int = Field(ge=1)
    ts: datetime = Field(default_factory=utcnow)
    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    """A structured statement the next agent or engineer can use and re-check."""

    schema_version: int = SCHEMA_VERSION
    step: str = ""
    summary: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    uncertainty: str = ""
    evidence: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
