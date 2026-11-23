"""One row of the append-only ledger."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .base import SCHEMA_VERSION, utcnow
from .enums import TaskState


class LedgerRow(BaseModel):
    schema_version: int = SCHEMA_VERSION
    ts: datetime = Field(default_factory=utcnow)
    task_id: str
    run_id: str | None = None
    state: TaskState
    verdict: str | None = None
    minutes_human: float | None = None
    tokens: int | None = None
    usd: float | None = None
    escape: bool = False
    rework: bool = False
