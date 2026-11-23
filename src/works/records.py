"""Persisted records. Every one carries a schema version."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = 1


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class SourceKind(StrEnum):
    MANUAL = "manual"
    TRACKER = "tracker"
    DETECTOR = "detector"


class TaskKind(StrEnum):
    FIX = "fix"
    CHECK_CHANGE = "check-change"


class TaskState(StrEnum):
    QUEUED = "queued"
    REPRODUCING = "reproducing"
    REPRODUCED = "reproduced"
    PLANNING = "planning"
    PLAN_APPROVED = "plan_approved"
    BUILDING = "building"
    CHECKING = "checking"
    PROVED = "proved"
    WAITING_REVIEW = "waiting_review"
    WAITING_CI = "waiting_ci"
    WAITING_DEPLOY = "waiting_deploy"
    RELEASING = "releasing"
    RELEASED = "released"
    REVERTED = "reverted"
    BLOCKED = "blocked"


class StopReason(StrEnum):
    COMPLETED = "completed"
    NOT_REPRODUCIBLE = "not_reproducible"
    NEEDS_PLAN_APPROVAL = "needs_plan_approval"
    HARNESS_FAILED = "harness_failed"
    POLICY_VIOLATION = "policy_violation"
    TESTS_FAILED = "tests_failed"
    CHALLENGE_FAILED = "challenge_failed"
    VERDICT_FAILED = "verdict_failed"
    BUDGET_EXCEEDED = "budget_exceeded"
    FLAKY_TEST = "flaky_test"
    CONFLICT = "conflict"
    CONFIG_ERROR = "config_error"
    INTERNAL_ERROR = "internal_error"


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"


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


class Challenge(BaseModel):
    """A separate reviewer's verdict on the builder's work."""

    schema_version: int = SCHEMA_VERSION
    allow: bool
    reason: str = ""
    concerns: list[str] = Field(default_factory=list)
    model: str = "unknown"
    provider: str = "unknown"
    credential_split: bool = False
    tokens: int = 0
    usd: float = 0.0
    prompt_sha256: str | None = None


class CommandRecord(BaseModel):
    schema_version: int = SCHEMA_VERSION
    step: str
    argv: list[str]
    cwd: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False
    output_sha256: str
    stdout_tail: str = ""
    stderr_tail: str = ""


class ScenarioOutcome(BaseModel):
    schema_version: int = SCHEMA_VERSION
    id: str
    priority: Priority
    weight: float
    passed: bool
    exit_code: int
    duration_ms: int
    output_sha256: str


class Verdict(BaseModel):
    schema_version: int = SCHEMA_VERSION
    run_id: str
    allow: bool
    reason: str
    p0_failed: list[str] = Field(default_factory=list)
    p1_pass_rate: float
    outcomes: list[ScenarioOutcome] = Field(default_factory=list)


class RunRecord(BaseModel):
    schema_version: int = SCHEMA_VERSION
    run_id: str
    task_id: str
    flow: str
    state: TaskState
    stop_reason: StopReason
    base_commit: str | None = None
    checks_sha: str | None = None
    task_kind: str = "fix"
    risk_level: str | None = None
    risk_reasons: list[str] = Field(default_factory=list)
    decision_verb: str | None = None
    decision_id: str | None = None
    model: str | None = None
    provider: str | None = None
    plan_id: str | None = None
    plan_hash: str | None = None
    planner_mode: str | None = None
    planner_provider: str | None = None
    planner_model: str | None = None
    planner_tokens: int = 0
    planner_usd: float = 0.0
    plan_deviations: list[str] = Field(default_factory=list)
    verifier: str = "local"
    verifier_isolation: str = "process"
    verifier_model: str | None = None
    verifier_provider: str | None = None
    provider_split: bool = False
    credential_split: bool = False
    attempts: int = 0
    tokens: int = 0
    usd: float = 0.0
    builder_tokens: int = 0
    builder_usd: float = 0.0
    verifier_tokens: int = 0
    verifier_usd: float = 0.0
    verification_share: float = 0.0
    started_at: datetime
    finished_at: datetime
    duration_ms: int = 0
    evidence_md: str | None = None


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
