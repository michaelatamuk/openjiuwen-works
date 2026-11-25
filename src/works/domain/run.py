"""Run, command, scenario and verdict records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .base import SCHEMA_VERSION
from .enums import Priority, StopReason, TaskState


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
    prompt_sha256: str | None = None
    harness: str | None = None
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
