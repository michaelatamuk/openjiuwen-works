"""The task record and its small value objects."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .base import SCHEMA_VERSION, utcnow
from .enums import SourceKind, TaskKind, TaskState

Severity = Literal["S1", "S2", "S3", "S4"]


class Source(BaseModel):
    """Where a signal came from, plus the context the source actually supplied.

    Only `kind` and `ref` are required, so every task written before this model existed still
    loads. `dedupe_key` is the identity used for duplicate detection: a webhook delivery, a tracker
    issue and a manually pasted link can all point at the same problem.
    """

    kind: SourceKind
    ref: str = Field(min_length=1)
    title: str = ""
    severity: Severity | None = None
    labels: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    author: str | None = None
    channel: str | None = None
    reproduction_hint: str | None = None
    dedupe_key: str | None = None
    received_at: datetime | None = None

    @field_validator("ref", "title")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        return value.strip()

    @field_validator("author", "channel", "reproduction_hint", "dedupe_key")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @property
    def identity(self) -> str:
        return self.dedupe_key or self.ref


class Budget(BaseModel):
    tokens: int = 400_000
    usd: float = 10.0
    wall_minutes: int = 60
    ci_minutes: int = 30


class Scope(BaseModel):
    paths_allow: list[str] = Field(default_factory=list)
    paths_deny: list[str] = Field(default_factory=list)


class Task(BaseModel):
    schema_version: int = SCHEMA_VERSION
    id: str
    flow: str
    product: str
    repo: str
    source: Source
    kind: TaskKind = TaskKind.FIX
    state: TaskState = TaskState.QUEUED
    budget: Budget = Field(default_factory=Budget)
    scope: Scope = Field(default_factory=Scope)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    attempts: int = 0
    waiting_on: str | None = None
    wake_on: str | None = None
    wake_deadline: datetime | None = None
    wake_next: TaskState | None = None
    wake_default: TaskState | None = None
