"""Run-scoped state shared by the supervisor and its collaborators."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from works.adapters.harness.base import Proposal
from works.adapters.processes.runner import CommandResult
from works.application.approvals.decisions import GateVerdict
from works.application.execution.scenarios import ScenarioSet
from works.application.reproduce.detect import Detection
from works.domain.errors import StateError
from works.domain.evidence import Artifact
from works.domain.flow import FlowSpec
from works.domain.policy import PolicyReport
from works.domain.records import (
    Challenge,
    CommandRecord,
    StopReason,
    Task,
    TaskState,
    Verdict,
)
from works.domain.review import SpecialistReview
from works.domain.risk import RiskRating


@dataclass
class RunContext:
    task: Task
    flow: FlowSpec
    run_id: str
    run_dir: Path
    worktree: Path | None
    base_commit: str | None = None
    checks_sha: str | None = None
    checks_source: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    commands: list[CommandRecord] = field(default_factory=list)
    reproduce: CommandRecord | None = None
    reproduction: Detection | None = None
    reproduction_attempts: int = 1
    attempt: int = 1
    baseline: CommandResult | None = None
    retry_requested: bool = False
    reproduction_stable: bool = True
    reproduction_env: dict[str, str] = field(default_factory=dict)
    test: CommandRecord | None = None
    preview: CommandRecord | None = None
    artifacts: list[Artifact] = field(default_factory=list)
    memory_recall: list[str] = field(default_factory=list)
    proposal: Proposal | None = None
    verdict: Verdict | None = None
    challenge: Challenge | None = None
    specialists: list[SpecialistReview] = field(default_factory=list)
    policy: PolicyReport = field(default_factory=lambda: PolicyReport(ok=True))
    risk: RiskRating | None = None
    decisions: list[GateVerdict] = field(default_factory=list)
    would_block: list[str] = field(default_factory=list)
    plan: dict[str, Any] = field(default_factory=dict)
    plan_deviations: list[str] = field(default_factory=list)
    scenario_set: ScenarioSet | None = None
    scenario_dir: Path | None = None
    state: TaskState = TaskState.QUEUED
    stop_reason: StopReason = StopReason.COMPLETED
    error: str | None = None


def new_run_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(tz=UTC)).strftime("%Y%m%dT%H%M%S")
    return f"r-{stamp}-{secrets.token_hex(3)}"


def _required[T](value: T | None, what: str) -> T:
    if value is None:
        raise StateError(f"{what} is not set; the run cannot continue")
    return value
