"""The task record and its small value objects."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from .base import SCHEMA_VERSION, utcnow
from .enums import SourceKind, TaskKind, TaskState


class Source(BaseModel):
    kind: SourceKind
    ref: str = Field(min_length=1)
    title: str = ""

    @field_validator("ref", "title")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


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
