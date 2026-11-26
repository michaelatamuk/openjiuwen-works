"""The evidence record: what a proof page contains."""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, Field

from works.adapters.git.repo import DiffStat
from works.application.approvals.decisions import GateVerdict
from works.domain.advisory import AdvisoryRef
from works.domain.policy import PolicyReport, Violation
from works.domain.records import (
    Challenge,
    CommandRecord,
    Finding,
    Priority,
    StopReason,
    TaskState,
    Verdict,
)
from works.domain.review import SpecialistReview
from works.domain.risk import RiskRating

MAX_DIFF_CHARS = 60_000


class DiffStatRow(BaseModel):
    path: str
    added: int
    removed: int

    @classmethod
    def from_stat(cls, stat: DiffStat) -> DiffStatRow:
        return cls(path=stat.path, added=stat.added, removed=stat.removed)


class Artifact(BaseModel):
    kind: str
    path: str
    sha256: str
    description: str = ""


class ModelCall(BaseModel):
    """One model invocation: who answered, with which model and adapter, and what it cost."""

    stage: str
    provider: str = "unknown"
    model: str = "unknown"
    version: str = "unknown"
    tokens: int = 0
    usd: float = 0.0


class Evidence(BaseModel):
    schema_version: int = 1
    run_id: str
    task_id: str
    task_title: str = ""
    flow: str
    product: str
    source: str
    reproduction_hint: str | None = None
    reproduction_command: list[str] = Field(default_factory=list)
    reproduction_source: str | None = None
    reproduction_attempts: int = 1
    reproduction_stable: bool = True
    reproduction_env: dict[str, str] = Field(default_factory=dict)
    task_kind: str = "fix"
    base_commit: str | None = None
    checks_sha: str | None = None
    state: TaskState
    stop_reason: StopReason
    model: str | None = None
    provider: str | None = None
    verifier: str = "local"
    verifier_isolation: str = "process"
    verifier_model: str | None = None
    verifier_provider: str | None = None
    provider_split: bool = False
    credential_split: bool = False
    prompt_name: str | None = None
    prompt_sha256: str | None = None
    harness: str | None = None
    plan_id: str | None = None
    plan_hash: str | None = None
    plan_summary: str | None = None
    planner_mode: str | None = None
    planner_provider: str | None = None
    planner_model: str | None = None
    planner_tokens: int = 0
    planner_usd: float = 0.0
    plan_estimated_tokens: int = 0
    plan_estimated_usd: float = 0.0
    plan_estimated_minutes: int = 0
    plan_deviations: list[str] = Field(default_factory=list)
    tokens: int = 0
    usd: float = 0.0
    builder_tokens: int = 0
    builder_usd: float = 0.0
    verifier_tokens: int = 0
    verifier_usd: float = 0.0
    model_calls: list[ModelCall] = Field(default_factory=list)
    verification_share: float = 0.0
    duration_ms: int = 0
    attempts: int = 1
    baseline_exit: int | None = None
    baseline_output_sha256: str | None = None
    skipped_checks: list[str] = Field(default_factory=list)
    event_root: str | None = None
    event_seq: int | None = None
    redactions: list[str] = Field(default_factory=list)
    runtime: dict[str, str] = Field(default_factory=dict)
    files_changed: list[str] = Field(default_factory=list)
    diff_stat: list[DiffStatRow] = Field(default_factory=list)
    policy: PolicyReport = Field(default_factory=lambda: PolicyReport(ok=True))
    risk: RiskRating | None = None
    advisory: AdvisoryRef | None = None
    specialists: list[SpecialistReview] = Field(default_factory=list)
    decision: GateVerdict | None = None
    reproduce: CommandRecord | None = None
    test: CommandRecord | None = None
    preview: CommandRecord | None = None
    verdict: Verdict | None = None
    challenge: Challenge | None = None
    findings: list[Finding] = Field(default_factory=list)
    features: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    memory_recall: list[str] = Field(default_factory=list)
    would_block: list[str] = Field(default_factory=list)
    not_tested: list[str] = Field(default_factory=list)
    diff: str = ""
    diff_sha256: str = ""
    proof_sha256: str = ""
    summary: str = ""

    def bind(self) -> Evidence:
        """Bind the page to its own content and to the diff."""
        diff_hash = hashlib.sha256(self.diff.encode("utf-8")).hexdigest()
        payload = self.model_copy(update={"diff_sha256": diff_hash, "proof_sha256": ""})
        exclude = {"proof_sha256"}
        if not self.task_title:
            # Preserve the historical proof hash for evidence that predates titles.
            exclude.add("task_title")
        if not self.summary:
            # Same for records written before the plain-language summary existed.
            exclude.add("summary")
        if self.advisory is None:
            # And for every proof written before advisories existed.
            exclude.add("advisory")
        if not self.specialists:
            # And for every proof written before specialist reviews existed.
            exclude.add("specialists")
        if not any(
            (
                self.plan_id,
                self.plan_hash,
                self.plan_summary,
                self.planner_mode,
                self.planner_provider,
                self.planner_model,
                self.planner_tokens,
                self.planner_usd,
                self.plan_deviations,
            )
        ):
            # Preserve the historical proof hash for evidence that predates plans.
            exclude |= {
                "plan_id",
                "plan_hash",
                "plan_summary",
                "planner_mode",
                "planner_provider",
                "planner_model",
                "planner_tokens",
                "planner_usd",
                "plan_deviations",
            }
        canonical = payload.model_dump_json(exclude=exclude)
        proof_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return self.model_copy(update={"diff_sha256": diff_hash, "proof_sha256": proof_hash})


def violations_report(violations: list[Violation]) -> PolicyReport:
    return PolicyReport(ok=not violations, violations=violations)


def priority_order(priority: Priority) -> int:
    return 0 if priority is Priority.P0 else 1
