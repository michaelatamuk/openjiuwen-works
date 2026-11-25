"""Plan records, enums and pure helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from works.domain.base import utcnow

SCHEMA_VERSION = 1


class PlanMode(StrEnum):
    DETERMINISTIC = "deterministic"
    SHADOW = "shadow"
    ASSISTED = "assisted"
    DEEP = "deep"
    SPEC = "spec"
    AUTO = "auto"


PLAN_MODES: tuple[PlanMode, ...] = (
    PlanMode.DETERMINISTIC,
    PlanMode.SHADOW,
    PlanMode.ASSISTED,
    PlanMode.DEEP,
    PlanMode.SPEC,
    PlanMode.AUTO,
)


class PlanStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    FROZEN = "frozen"
    SUPERSEDED = "superseded"
    SHADOW = "shadow"
    ALTERNATIVE = "alternative"


class PlanStep(BaseModel):
    schema_version: int = SCHEMA_VERSION
    id: str = ""
    node: str
    title: str = ""
    intent: str = ""
    files: list[str] = Field(default_factory=list)
    reads: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    done_when: str = ""
    risk: str = "low"
    depends_on: list[str] = Field(default_factory=list)
    reversible: bool = True


class PlanProposal(BaseModel):
    """What a planner returns before it is bound to the deterministic contract."""

    schema_version: int = SCHEMA_VERSION
    summary: str = ""
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    steps: list[PlanStep] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)
    rollback: str = ""
    estimated_tokens: int = Field(default=0, ge=0)
    estimated_usd: float = Field(default=0.0, ge=0.0)
    estimated_minutes: int = Field(default=0, ge=0)
    notes: list[str] = Field(default_factory=list)
    requirements_md: str = ""
    design_md: str = ""
    tasks_md: str = ""


class PlanProvenance(BaseModel):
    schema_version: int = SCHEMA_VERSION
    mode: str = PlanMode.DETERMINISTIC.value
    planner: str = "deterministic"
    provider: str | None = None
    model: str | None = None
    prompt_sha256: str | None = None
    tokens: int = Field(default=0, ge=0)
    usd: float = Field(default=0.0, ge=0.0)
    duration_ms: int = Field(default=0, ge=0)
    fallback: bool = False
    error: str | None = None


class PlanValidation(BaseModel):
    schema_version: int = SCHEMA_VERSION
    ok: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)


class PlanCritique(BaseModel):
    schema_version: int = SCHEMA_VERSION
    allow: bool = True
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    findings: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    model: str = ""
    provider: str = ""
    prompt_sha256: str | None = None
    tokens: int = Field(default=0, ge=0)
    usd: float = Field(default=0.0, ge=0.0)


class PlanVersion(BaseModel):
    schema_version: int = SCHEMA_VERSION
    plan_id: str
    task_id: str
    version: int = Field(ge=1)
    status: PlanStatus = PlanStatus.DRAFT
    created_at: datetime = Field(default_factory=utcnow)
    flow: str
    product: str
    base_commit: str
    checks_sha: str
    checks_source: str
    scenario_set: str
    scenario_ids: list[str] = Field(default_factory=list)
    scenario_sha: str = ""
    summary: str = ""
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    steps: list[PlanStep] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)
    rollback: str = ""
    estimated_tokens: int = Field(default=0, ge=0)
    estimated_usd: float = Field(default=0.0, ge=0.0)
    estimated_minutes: int = Field(default=0, ge=0)
    requirements_md: str = ""
    design_md: str = ""
    tasks_md: str = ""
    provenance: PlanProvenance = Field(default_factory=PlanProvenance)
    validation: PlanValidation | None = None
    critique: PlanCritique | None = None
    hash: str = ""
    approved_by: str | None = None
    approved_at: datetime | None = None

    @property
    def nodes(self) -> list[str]:
        return sorted({step.node for step in self.steps})


def plan_hash(plan: PlanVersion) -> str:
    payload = plan.model_dump(
        mode="json",
        exclude={
            "created_at",
            "hash",
            "status",
            "validation",
            "critique",
            "approved_by",
            "approved_at",
            "provenance",
        },
    )
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def plan_deviations(plan: PlanVersion, touched: list[str]) -> list[str]:
    """Files changed outside the plan's named write scope.

    A deterministic plan names no files, so it cannot drift. An assisted plan with a concrete file
    list can; the supervisor records the difference instead of hiding it.
    """
    planned = {path for step in plan.steps for path in step.files}
    if not planned:
        return []
    return sorted(set(touched) - planned)
