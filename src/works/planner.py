"""Plan artefacts: deterministic contract, optional model proposal, lint and versioning.

The flow is the contract. A planner may add detail inside a flow node, but it cannot remove a
required node, approve itself, or turn a model mistake into an executable step. Every plan version
is immutable, hash-addressed and stored next to the task.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from .config import WorksPaths
from .errors import ConfigError, NotFoundError
from .flow import FlowSpec, Node, NodeKind
from .policy import check_paths
from .queue import atomic_write
from .records import utcnow
from .risk import rate_risk
from .scenarios import ScenarioSet
from .trusted import is_check_path

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


@dataclass(frozen=True)
class PlannerContext:
    """The bounded, reproducible input to a planner."""

    task_id: str
    product: str
    task_kind: str
    source_ref: str
    source_title: str
    flow: FlowSpec
    base_commit: str
    checks_sha: str
    checks_source: str
    scenario_set: Path
    scenarios: ScenarioSet
    repo: Path
    budget_tokens: int
    budget_usd: float
    memory: tuple[str, ...] = ()
    prior_plans: tuple[dict[str, Any], ...] = ()
    findings: tuple[str, ...] = ()
    file_tree: tuple[str, ...] = ()
    manifests: tuple[tuple[str, str], ...] = ()
    readme: str = ""

    @property
    def p0_ids(self) -> list[str]:
        return list(self.scenarios.p0_ids)

    @property
    def p1_ids(self) -> list[str]:
        return list(self.scenarios.p1_ids)


@dataclass(frozen=True)
class PlannerOutput:
    proposal: PlanProposal
    provenance: PlanProvenance


@dataclass(frozen=True)
class RepositoryContext:
    file_tree: tuple[str, ...] = ()
    manifests: tuple[tuple[str, str], ...] = ()
    readme: str = ""


_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".hypothesis",
        "dist",
        "build",
        "target",
        "runs",
        "queue",
        "worktrees",
        "logs",
    }
)
_MANIFESTS = ("pyproject.toml", "package.json", "Cargo.toml", "go.mod", "requirements.txt")


def collect_repository_context(repo: Path, *, limit: int = 400) -> RepositoryContext:
    """A bounded, deterministic view of the repository for a planner prompt."""
    files: list[str] = []
    if repo.exists():
        for path in sorted(repo.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(repo)
            if any(part in _SKIP_DIRS for part in relative.parts):
                continue
            files.append(relative.as_posix())
            if len(files) >= limit:
                break
    manifests: list[tuple[str, str]] = []
    for name in _MANIFESTS:
        path = repo / name
        if path.is_file():
            manifests.append((name, _read_bounded(path)))
    readme = ""
    for name in ("README.md", "README.rst", "README.txt"):
        path = repo / name
        if path.is_file():
            readme = _read_bounded(path)
            break
    return RepositoryContext(file_tree=tuple(files), manifests=tuple(manifests), readme=readme)


def _read_bounded(path: Path, limit: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


class Planner(Protocol):
    name: str

    async def draft(self, context: PlannerContext) -> PlannerOutput: ...


class Critic(Protocol):
    name: str

    async def review(self, context: PlannerContext, plan: PlanVersion) -> PlanCritique: ...


def _node_step(node: Node, order: int, previous: str | None) -> PlanStep:
    kind = "deterministic command" if node.kind is NodeKind.DETERMINISTIC else "agent turn"
    intents = {
        "reproduce": "Reproduce the reported behaviour and capture the failing check.",
        "build": "Edit the minimum production code needed to make the reproduction pass.",
        "test": "Run the repository tests and the declared scenarios.",
        "challenge": "Review the diff independently and return a verdict.",
        "preview": "Run the preview and attach its artifacts.",
    }
    done = {
        "reproduce": "the reproduction fails on the base commit",
        "build": "the reproduction and tests pass",
        "test": "the tests and scenarios pass",
        "challenge": "the challenger returns allow",
        "preview": "the preview exits successfully",
    }
    commands = [node.cmd] if node.cmd else []
    return PlanStep(
        id=f"det-{order}-{node.id}",
        node=node.id,
        title=f"{node.id}: {kind}",
        intent=intents.get(node.id, f"Run the flow node {node.id!r} as declared."),
        commands=commands,
        done_when=done.get(node.id, "the node records a terminal result"),
        risk="low",
        depends_on=[previous] if previous else [],
    )


def deterministic_proposal(context: PlannerContext) -> PlanProposal:
    """The contract skeleton: one step per flow node, scenario coverage, safe defaults."""
    steps: list[PlanStep] = []
    previous: str | None = None
    for order, node in enumerate(context.flow.nodes, start=1):
        step = _node_step(node, order, previous)
        steps.append(step)
        previous = step.id
    p0 = ", ".join(context.p0_ids) or "none declared"
    p1 = ", ".join(context.p1_ids) or "none declared"
    verification = [
        "Run the flow test node.",
        f"P0 scenarios: {p0}.",
        f"P1 scenarios: {p1}.",
    ]
    if any(node.id == "challenge" for node in context.flow.nodes):
        verification.append("Run the independent challenge node.")
    return PlanProposal(
        summary=(
            f"Deterministic plan for {context.flow.flow} on {context.product}: "
            f"{len(context.flow.nodes)} flow nodes and "
            f"{len(context.scenarios.scenarios)} scenarios."
        ),
        assumptions=[
            "The flow nodes and the scenario set are the source of truth.",
            "The builder works in an isolated worktree and does not commit.",
        ],
        steps=steps,
        risks=[
            "This plan is a contract skeleton; file-level detail is chosen during the build turn."
        ],
        verification=verification,
        rollback="Discard the worktree; the builder does not commit.",
        notes=["Deterministic mode: no model planned this version."],
    )


def _normalise_steps(steps: list[PlanStep]) -> list[PlanStep]:
    seen: set[str] = set()
    normalised: list[PlanStep] = []
    for index, step in enumerate(steps, start=1):
        identifier = step.id.strip() or f"s{index}"
        candidate = identifier
        suffix = 2
        while candidate in seen:
            candidate = f"{identifier}-{suffix}"
            suffix += 1
        seen.add(candidate)
        normalised.append(step.model_copy(update={"id": candidate}))
    return normalised


def merge_proposal(
    base: PlanProposal, proposal: PlanProposal, context: PlannerContext
) -> PlanProposal:
    """Keep the deterministic contract and let a model add detail inside its nodes.

    Missing required nodes get their deterministic step back. Unknown node names are kept so the
    linter can reject them instead of silently dropping a model mistake.
    """
    by_node: dict[str, list[PlanStep]] = {}
    for step in _normalise_steps(proposal.steps):
        by_node.setdefault(step.node, []).append(step)

    base_by_node: dict[str, PlanStep] = {step.node: step for step in base.steps}
    merged: list[PlanStep] = []
    for node in context.flow.nodes:
        model_steps = by_node.get(node.id, [])
        if model_steps:
            merged.extend(model_steps)
        elif node.id in base_by_node:
            merged.append(base_by_node[node.id])
    # Unknown nodes are intentionally kept for the linter.
    for node_id, steps in by_node.items():
        if node_id not in {node.id for node in context.flow.nodes}:
            merged.extend(steps)

    def node_order(step: PlanStep) -> tuple[int, int]:
        ids = [node.id for node in context.flow.nodes]
        try:
            return (ids.index(step.node), 0)
        except ValueError:
            return (len(ids), 0)

    merged.sort(key=node_order)
    return PlanProposal(
        summary=proposal.summary.strip() or base.summary,
        assumptions=_unique([*base.assumptions, *proposal.assumptions]),
        open_questions=_unique(proposal.open_questions),
        steps=_normalise_steps(merged),
        risks=_unique(proposal.risks) or base.risks,
        verification=_unique(proposal.verification) or base.verification,
        rollback=proposal.rollback.strip() or base.rollback,
        estimated_tokens=proposal.estimated_tokens,
        estimated_usd=proposal.estimated_usd,
        estimated_minutes=proposal.estimated_minutes,
        notes=_unique(proposal.notes) or base.notes,
        requirements_md=proposal.requirements_md.strip(),
        design_md=proposal.design_md.strip(),
        tasks_md=proposal.tasks_md.strip(),
    )


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


_TEST_PATH = re.compile(r"(^|/)(?:tests?/|test_[^/]*\.py$|[^/]*_test\.py$|conftest\.py$)")
_DANGEROUS_COMMAND = re.compile(
    r"(^|[\s;&|])(?:"
    r"rm|del|rd|rmdir|shutdown|sudo|ssh|scp|curl|wget|invoke-webrequest|"
    r"git\s+(?:push|reset\s+--hard|clean)|"
    r"pip\s+install|npm\s+install|yarn\s+add|pnpm\s+add|"
    r"docker\s+push|kubectl\s+apply|terraform\s+apply"
    r")(?=$|[\s;&|])",
    re.IGNORECASE,
)


def validate_plan(
    proposal: PlanProposal,
    context: PlannerContext,
    *,
    allow_test_edits: bool = False,
) -> PlanValidation:
    """Deterministic lint. A model cannot override an error in this function."""
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    checks.append("summary")
    if not proposal.summary.strip():
        errors.append("the plan needs a summary")

    checks.append("steps")
    if not proposal.steps:
        errors.append("the plan needs at least one step")

    flow_ids = [node.id for node in context.flow.nodes]
    plan_ids = {step.node for step in proposal.steps}
    checks.append("node-coverage")
    for node_id in flow_ids:
        if node_id not in plan_ids:
            errors.append(f"the plan does not cover the required flow node {node_id!r}")
    for node_id in sorted(plan_ids - set(flow_ids)):
        errors.append(f"the plan uses unknown flow node {node_id!r}")

    checks.append("step-detail")
    for step in proposal.steps:
        if not step.title.strip():
            errors.append(f"step {step.id or step.node!r} needs a title")
        if not step.done_when.strip():
            warnings.append(f"step {step.id or step.node!r} has no done_when")

    checks.append("scenario-coverage")
    verification = " ".join(proposal.verification).lower()
    for scenario_id in context.p0_ids:
        if scenario_id.lower() not in verification and scenario_id not in proposal.notes:
            warnings.append(f"P0 scenario {scenario_id!r} is not named in verification")

    checks.append("paths")
    all_files = [path for step in proposal.steps for path in step.files]
    all_reads = [path for step in proposal.steps for path in step.reads]
    violations = check_paths(all_files, context.flow.paths)
    for violation in violations:
        if (
            context.task_kind == "check-change"
            and is_check_path(violation.path)
            and violation.reason == "denied by policy"
        ):
            continue
        if _TEST_PATH.search(violation.path) and context.task_kind != "check-change":
            errors.append(f"path {violation.path!r} is a test path; a fix task cannot edit tests")
            continue
        errors.append(f"path {violation.path!r}: {violation.reason}")
    for raw in all_files:
        if raw.startswith(("/", "\\", "~")) or ".." in Path(raw).parts:
            errors.append(f"path {raw!r} must be a safe relative repository path")
        elif is_check_path(raw) and context.task_kind != "check-change" and not allow_test_edits:
            errors.append(
                f"path {raw!r} is a protected check path; a check change needs a check-change task"
            )
    for raw in all_reads:
        if raw.startswith(("/", "\\", "~")) or ".." in Path(raw).parts:
            errors.append(f"read path {raw!r} must be a safe relative repository path")

    checks.append("commands")
    for step in proposal.steps:
        for command in step.commands:
            if _DANGEROUS_COMMAND.search(command):
                errors.append(
                    f"step {step.id or step.node!r} proposes a destructive or "
                    f"side-effecting command: {command!r}"
                )

    checks.append("budget")
    if proposal.estimated_tokens and proposal.estimated_tokens > context.budget_tokens:
        errors.append(
            f"the plan estimates {proposal.estimated_tokens} tokens, over the "
            f"{context.budget_tokens} budget"
        )
    if proposal.estimated_usd and proposal.estimated_usd > context.budget_usd:
        errors.append(
            f"the plan estimates ${proposal.estimated_usd:.4f}, over the "
            f"${context.budget_usd:.4f} budget"
        )

    checks.append("rollback")
    if not proposal.rollback.strip():
        errors.append("the plan needs a rollback statement")

    checks.append("spec")
    if proposal.requirements_md.strip() or proposal.design_md.strip() or proposal.tasks_md.strip():
        for name, value in (
            ("requirements", proposal.requirements_md),
            ("design", proposal.design_md),
            ("tasks", proposal.tasks_md),
        ):
            if not value.strip():
                warnings.append(f"spec mode has an empty {name} document")

    checks.append("open-questions")
    if proposal.open_questions:
        warnings.append(
            f"the plan has {len(proposal.open_questions)} open question(s); a person must resolve "
            "or accept them at the gate"
        )

    return PlanValidation(ok=not errors, errors=errors, warnings=warnings, checks=checks)


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


def make_plan_version(
    context: PlannerContext,
    proposal: PlanProposal,
    *,
    version: int,
    mode: PlanMode,
    provenance: PlanProvenance,
    validation: PlanValidation,
    critique: PlanCritique | None = None,
    status: PlanStatus | None = None,
) -> PlanVersion:
    plan = PlanVersion(
        plan_id=f"p-{context.task_id}-v{version}",
        task_id=context.task_id,
        version=version,
        status=status or (PlanStatus.VALIDATED if validation.ok else PlanStatus.DRAFT),
        flow=context.flow.flow,
        product=context.product,
        base_commit=context.base_commit,
        checks_sha=context.checks_sha,
        checks_source=context.checks_source,
        scenario_set=str(context.scenario_set),
        scenario_ids=[scenario.id for scenario in context.scenarios.scenarios],
        summary=proposal.summary,
        assumptions=proposal.assumptions,
        open_questions=proposal.open_questions,
        notes=proposal.notes,
        steps=proposal.steps,
        risks=proposal.risks,
        verification=proposal.verification,
        rollback=proposal.rollback,
        estimated_tokens=proposal.estimated_tokens,
        estimated_usd=proposal.estimated_usd,
        estimated_minutes=proposal.estimated_minutes,
        requirements_md=proposal.requirements_md,
        design_md=proposal.design_md,
        tasks_md=proposal.tasks_md,
        provenance=provenance,
        validation=validation,
        critique=critique,
    )
    return plan.model_copy(update={"hash": plan_hash(plan)})


def apply_critique(validation: PlanValidation, critique: PlanCritique | None) -> PlanValidation:
    if critique is None or critique.allow:
        return validation
    return validation.model_copy(
        update={
            "ok": False,
            "errors": [
                *validation.errors,
                "the independent critic rejected the plan: "
                f"{critique.concerns or critique.findings}",
            ],
        }
    )


class DeterministicPlanner:
    name = "deterministic"

    async def draft(self, context: PlannerContext) -> PlannerOutput:
        return PlannerOutput(
            proposal=deterministic_proposal(context),
            provenance=PlanProvenance(mode=PlanMode.DETERMINISTIC.value),
        )


class PlanStore:
    """Immutable plan versions under the task directory."""

    def __init__(self, paths: WorksPaths) -> None:
        self._paths = paths

    def directory(self, task_id: str) -> Path:
        return self._paths.task_dir(task_id) / "plans"

    def _path(self, task_id: str, version: int) -> Path:
        return self.directory(task_id) / f"v{version}.json"

    def _shadow_path(self, task_id: str, version: int) -> Path:
        return self.directory(task_id) / f"shadow-v{version}.json"

    def versions(self, task_id: str) -> list[int]:
        directory = self.directory(task_id)
        if not directory.exists():
            return []
        versions: list[int] = []
        for path in directory.glob("v*.json"):
            try:
                versions.append(int(path.stem[1:]))
            except ValueError:
                continue
        return sorted(versions)

    def next_version(self, task_id: str) -> int:
        versions = self.versions(task_id)
        return (versions[-1] + 1) if versions else 1

    def save(self, plan: PlanVersion) -> PlanVersion:
        directory = self.directory(plan.task_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = self._path(plan.task_id, plan.version)
        if path.exists():
            raise ConfigError(f"plan version {plan.version} already exists for {plan.task_id}")
        atomic_write(path, plan.model_dump_json(indent=2) + "\n")
        atomic_write(
            path.with_suffix(".md"),
            plan_markdown(plan) + "\n",
        )
        for suffix, text in (
            ("requirements.md", plan.requirements_md),
            ("design.md", plan.design_md),
            ("tasks.md", plan.tasks_md),
        ):
            if text.strip():
                atomic_write(path.with_name(f"{path.stem}.{suffix}"), text + "\n")
        return plan

    def save_alternative(self, plan: PlanVersion, label: str) -> PlanVersion:
        directory = self.directory(plan.task_id)
        directory.mkdir(parents=True, exist_ok=True)
        version = len(list(directory.glob(f"alt-{label}-v*.json"))) + 1
        alternative = plan.model_copy(
            update={
                "plan_id": f"alt-{label}-{plan.task_id}-v{version}",
                "version": version,
                "status": PlanStatus.ALTERNATIVE,
            }
        )
        path = directory / f"alt-{label}-v{version}.json"
        atomic_write(path, alternative.model_dump_json(indent=2) + "\n")
        atomic_write(path.with_suffix(".md"), plan_markdown(alternative) + "\n")
        return alternative

    def alternatives(self, task_id: str) -> dict[str, PlanVersion]:
        directory = self.directory(task_id)
        found: dict[str, PlanVersion] = {}
        if not directory.exists():
            return found
        for path in sorted(directory.glob("alt-*-v*.json")):
            plan = PlanVersion.model_validate_json(path.read_text(encoding="utf-8"))
            found[plan.plan_id] = plan
        return found

    def save_shadow(self, plan: PlanVersion) -> PlanVersion:
        directory = self.directory(plan.task_id)
        directory.mkdir(parents=True, exist_ok=True)
        version = len(list(directory.glob("shadow-v*.json"))) + 1
        shadow = plan.model_copy(
            update={"plan_id": f"shadow-{plan.task_id}-v{version}", "version": version}
        )
        path = self._shadow_path(plan.task_id, version)
        atomic_write(path, shadow.model_dump_json(indent=2) + "\n")
        atomic_write(path.with_suffix(".md"), plan_markdown(shadow) + "\n")
        return shadow

    def approve(self, task_id: str, *, plan_id: str, plan_hash: str, by: str) -> PlanVersion:
        plan = self.load(task_id)
        if plan.plan_id != plan_id or plan.hash != plan_hash:
            raise ConfigError("the plan changed before it was approved; re-plan first")
        updated = plan.model_copy(
            update={
                "status": PlanStatus.APPROVED,
                "approved_by": by,
                "approved_at": utcnow(),
            }
        )
        path = self._path(task_id, plan.version)
        atomic_write(path, updated.model_dump_json(indent=2) + "\n")
        atomic_write(path.with_suffix(".md"), plan_markdown(updated) + "\n")
        return updated

    def mark_superseded(self, task_id: str, plan_id: str) -> None:
        for version in self.versions(task_id):
            plan = self.load(task_id, version)
            if plan.plan_id != plan_id:
                continue
            updated = plan.model_copy(update={"status": PlanStatus.SUPERSEDED})
            path = self._path(task_id, plan.version)
            atomic_write(path, updated.model_dump_json(indent=2) + "\n")
            atomic_write(path.with_suffix(".md"), plan_markdown(updated) + "\n")
            return

    def load(self, task_id: str, version: int | None = None) -> PlanVersion:
        selected = version or (self.versions(task_id)[-1] if self.versions(task_id) else None)
        if selected is None:
            raise NotFoundError(f"task {task_id} has no plan")
        path = self._path(task_id, selected)
        if not path.exists():
            raise NotFoundError(f"task {task_id} has no plan version {selected}")
        try:
            return PlanVersion.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ConfigError(f"{path} is not a valid plan: {exc}") from exc

    def shadow(self, task_id: str) -> PlanVersion | None:
        paths = sorted(self.directory(task_id).glob("shadow-v*.json"))
        if not paths:
            return None
        return PlanVersion.model_validate_json(paths[-1].read_text(encoding="utf-8"))

    def all(self, task_id: str) -> list[PlanVersion]:
        return [self.load(task_id, version) for version in self.versions(task_id)]


async def draft_plan(
    context: PlannerContext,
    *,
    store: PlanStore,
    mode: PlanMode | str,
    planner: Planner | None = None,
    critic: Critic | None = None,
) -> PlanVersion:
    """Draft, merge, lint and store one plan version.

    `shadow` always executes the deterministic plan and stores a model proposal beside it.
    `assisted` and `deep` fail closed when their model is missing or returns no steps.
    """
    selected = PlanMode(mode)
    base = deterministic_proposal(context)
    provenance = PlanProvenance(mode=selected.value)
    critique: PlanCritique | None = None

    if selected is PlanMode.DETERMINISTIC:
        proposal = base
        validation = validate_plan(proposal, context)
    elif selected is PlanMode.SHADOW:
        proposal = base
        validation = validate_plan(proposal, context)
        if planner is not None:
            try:
                output = await planner.draft(context)
                shadow_validation = validate_plan(output.proposal, context)
                shadow = make_plan_version(
                    context,
                    merge_proposal(base, output.proposal, context),
                    version=1,
                    mode=selected,
                    provenance=output.provenance.model_copy(update={"mode": selected.value}),
                    validation=shadow_validation,
                    status=PlanStatus.SHADOW,
                )
                store.save_shadow(shadow)
            except Exception as exc:
                # Shadow is observational: a model failure must never change the run, but it is
                # recorded for comparison.
                failed = make_plan_version(
                    context,
                    base,
                    version=1,
                    mode=selected,
                    provenance=PlanProvenance(
                        mode=selected.value,
                        planner=getattr(planner, "name", "unknown"),
                        error=str(exc),
                    ),
                    validation=validate_plan(base, context),
                    status=PlanStatus.SHADOW,
                )
                store.save_shadow(failed)
    else:
        if planner is None:
            if selected is not PlanMode.AUTO:
                raise ConfigError(f"planner mode {selected.value!r} needs a planner provider")
            proposal = base.model_copy(
                update={
                    "notes": [
                        *base.notes,
                        "Auto selected deterministic: no planner provider is available.",
                    ]
                }
            )
            validation = validate_plan(proposal, context)
            provenance = PlanProvenance(mode=PlanMode.AUTO.value)
        else:
            try:
                output = await planner.draft(context)
                if not output.proposal.steps:
                    raise ConfigError("the planner returned no steps")
            except ConfigError as exc:
                if selected is not PlanMode.AUTO:
                    raise
                proposal = base.model_copy(
                    update={
                        "notes": [
                            *base.notes,
                            f"Auto fell back to deterministic: {exc}",
                        ]
                    }
                )
                validation = validate_plan(proposal, context)
                provenance = PlanProvenance(mode=PlanMode.AUTO.value, error=str(exc))
            else:
                proposal = merge_proposal(base, output.proposal, context)
                provenance = output.provenance.model_copy(update={"mode": selected.value})
                validation = validate_plan(proposal, context)
                if not validation.ok and selected in (
                    PlanMode.ASSISTED,
                    PlanMode.DEEP,
                    PlanMode.SPEC,
                    PlanMode.AUTO,
                ):
                    repair = getattr(planner, "draft_with_feedback", None)
                    if callable(repair):
                        try:
                            repaired = await repair(context, proposal, validation.errors)
                        except Exception as exc:
                            provenance = provenance.model_copy(
                                update={"error": f"repair failed: {exc}"}
                            )
                        else:
                            proposal = merge_proposal(base, repaired.proposal, context)
                            provenance = repaired.provenance.model_copy(
                                update={
                                    "mode": selected.value,
                                    "tokens": provenance.tokens + repaired.provenance.tokens,
                                    "usd": provenance.usd + repaired.provenance.usd,
                                }
                            )
                            validation = validate_plan(proposal, context)
                            proposal = proposal.model_copy(
                                update={
                                    "notes": [
                                        *proposal.notes,
                                        "Repaired after deterministic lint.",
                                    ]
                                }
                            )
                if selected is PlanMode.SPEC:
                    missing_spec = [
                        name
                        for name, value in (
                            ("requirements_md", proposal.requirements_md),
                            ("design_md", proposal.design_md),
                            ("tasks_md", proposal.tasks_md),
                        )
                        if not value.strip()
                    ]
                    if missing_spec:
                        validation = validation.model_copy(
                            update={
                                "ok": False,
                                "errors": [
                                    *validation.errors,
                                    "spec mode needs requirements, design and tasks documents "
                                    f"(missing: {', '.join(missing_spec)})",
                                ],
                            }
                        )
                if selected in (PlanMode.DEEP, PlanMode.AUTO):
                    planned_files = [path for step in proposal.steps for path in step.files]
                    risk = rate_risk(paths=planned_files, diff_stat=[], flow=context.flow)
                    needs_critic = selected is PlanMode.DEEP or (
                        selected is PlanMode.AUTO
                        and risk.level.value == "high"
                        and critic is not None
                    )
                    if needs_critic:
                        if critic is None:
                            raise ConfigError("deep planner mode needs an independent critic")
                        preliminary = make_plan_version(
                            context,
                            proposal,
                            version=store.next_version(context.task_id),
                            mode=selected,
                            provenance=provenance,
                            validation=validation,
                        )
                        critique = await critic.review(context, preliminary)
                        validation = apply_critique(validation, critique)
                    if selected is PlanMode.AUTO:
                        effective = "deep" if critique is not None else "assisted"
                        proposal = proposal.model_copy(
                            update={
                                "notes": [
                                    *proposal.notes,
                                    f"Auto selected {effective} for {risk.level.value} risk.",
                                ]
                            }
                        )

    version = store.next_version(context.task_id)
    plan = make_plan_version(
        context,
        proposal,
        version=version,
        mode=selected,
        provenance=provenance,
        validation=validation,
        critique=critique,
    )
    return store.save(plan)


def plan_deviations(plan: PlanVersion, touched: list[str]) -> list[str]:
    """Files changed outside the plan's named write scope.

    A deterministic plan names no files, so it cannot drift. An assisted plan with a concrete file
    list can; the supervisor records the difference instead of hiding it.
    """
    planned = {path for step in plan.steps for path in step.files}
    if not planned:
        return []
    return sorted(set(touched) - planned)


def plan_brief(plan: PlanVersion) -> str:
    """A compact, model-readable brief of the approved plan."""
    lines = [f"Summary: {plan.summary}"]
    for step in plan.steps:
        details = [f"node={step.node}", f"done_when={step.done_when or 'not stated'}"]
        if step.files:
            details.append(f"files={', '.join(step.files)}")
        if step.reads:
            details.append(f"reads={', '.join(step.reads)}")
        if step.commands:
            details.append(f"commands={', '.join(step.commands)}")
        lines.append(f"- {step.title} ({'; '.join(details)})")
    if plan.verification:
        lines.append("Verification: " + "; ".join(plan.verification))
    if plan.assumptions:
        lines.append("Assumptions: " + "; ".join(plan.assumptions))
    if plan.open_questions:
        lines.append("Open questions: " + "; ".join(plan.open_questions))
    if plan.risks:
        lines.append("Risks: " + "; ".join(plan.risks))
    if plan.rollback:
        lines.append(f"Rollback: {plan.rollback}")
    return "\n".join(lines)


async def draft_alternatives(
    context: PlannerContext,
    *,
    store: PlanStore,
    mode: PlanMode | str,
    planners: dict[str, Planner],
    critic: Critic | None = None,
) -> dict[str, PlanVersion]:
    """Draft labelled alternatives with different planner prompts, without touching the run."""
    selected = PlanMode(mode)
    base = deterministic_proposal(context)
    results: dict[str, PlanVersion] = {}
    for label, planner in planners.items():
        output = await planner.draft(context)
        if not output.proposal.steps:
            raise ConfigError(f"alternative {label!r} returned no steps")
        proposal = merge_proposal(base, output.proposal, context)
        validation = validate_plan(proposal, context)
        provenance = output.provenance.model_copy(update={"mode": selected.value})
        critique = None
        if selected is PlanMode.DEEP:
            if critic is None:
                raise ConfigError("deep alternatives need an independent critic")
            preliminary = make_plan_version(
                context,
                proposal,
                version=1,
                mode=selected,
                provenance=provenance,
                validation=validation,
            )
            critique = await critic.review(context, preliminary)
            validation = apply_critique(validation, critique)
        plan = make_plan_version(
            context,
            proposal,
            version=1,
            mode=selected,
            provenance=provenance,
            validation=validation,
            critique=critique,
            status=PlanStatus.ALTERNATIVE,
        )
        results[label] = store.save_alternative(plan, label)
    return results


def plan_markdown(plan: PlanVersion) -> str:
    lines = [
        f"# Plan {plan.plan_id}",
        "",
        f"- Task: `{plan.task_id}`",
        f"- Flow: `{plan.flow}` / {plan.product}",
        f"- Status: `{plan.status.value}`",
        f"- Base commit: `{plan.base_commit}`",
        f"- Checks: `{plan.checks_sha}` ({plan.checks_source})",
        f"- Scenarios: {', '.join(plan.scenario_ids) or 'none'}",
        f"- Planner: `{plan.provenance.planner}`",
        f"- Provider/model: `{plan.provenance.provider or '-'}` / `{plan.provenance.model or '-'}`",
        f"- Cost: {plan.provenance.tokens} tokens / ${plan.provenance.usd:.4f}",
        f"- Hash: `{plan.hash}`",
        "",
        "## Summary",
        "",
        plan.summary,
        "",
    ]
    if plan.assumptions:
        lines += ["## Assumptions", "", *[f"- {item}" for item in plan.assumptions], ""]
    if plan.open_questions:
        lines += ["## Open questions", "", *[f"- {item}" for item in plan.open_questions], ""]
    if plan.notes:
        lines += ["## Notes", "", *[f"- {item}" for item in plan.notes], ""]
    if plan.requirements_md:
        lines += ["## Requirements", "", plan.requirements_md, ""]
    if plan.design_md:
        lines += ["## Design", "", plan.design_md, ""]
    if plan.tasks_md:
        lines += ["## Tasks", "", plan.tasks_md, ""]
    lines += ["## Steps", ""]
    for step in plan.steps:
        lines += [
            f"### {step.id} · {step.node} · {step.title}",
            "",
            step.intent,
            "",
            f"- Done when: {step.done_when or 'not stated'}",
            f"- Files: {', '.join(step.files) or 'none named'}",
            f"- Reads: {', '.join(step.reads) or 'none named'}",
            f"- Commands: {', '.join(step.commands) or 'none'}",
            f"- Risk: {step.risk}",
            "",
        ]
    if plan.risks:
        lines += ["## Risks", "", *[f"- {item}" for item in plan.risks], ""]
    if plan.verification:
        lines += ["## Verification", "", *[f"- {item}" for item in plan.verification], ""]
    lines += ["## Rollback", "", plan.rollback, ""]
    if plan.validation is not None:
        lines += [
            "## Lint",
            "",
            f"- OK: `{plan.validation.ok}`",
            *[f"- Error: {item}" for item in plan.validation.errors],
            *[f"- Warning: {item}" for item in plan.validation.warnings],
            "",
        ]
    if plan.critique is not None:
        lines += [
            "## Critique",
            "",
            f"- Allow: `{plan.critique.allow}`",
            f"- Score: {plan.critique.score:.2f}",
            *[f"- Finding: {item}" for item in plan.critique.findings],
            *[f"- Concern: {item}" for item in plan.critique.concerns],
            "",
        ]
    lines += ["## Provenance", "", "```json", plan.provenance.model_dump_json(indent=2), "```", ""]
    return "\n".join(lines)


def context_payload(context: PlannerContext) -> dict[str, Any]:
    return {
        "task_id": context.task_id,
        "product": context.product,
        "task_kind": context.task_kind,
        "source": {"ref": context.source_ref, "title": context.source_title},
        "flow": {
            "name": context.flow.flow,
            "nodes": [
                {
                    "id": node.id,
                    "kind": node.kind.value,
                    "required": node.required,
                    "mode": node.mode.value,
                    "cmd": node.cmd,
                }
                for node in context.flow.nodes
            ],
            "gates": [gate.model_dump(mode="json") for gate in context.flow.gates],
            "paths": context.flow.paths.model_dump(mode="json"),
            "budget": context.flow.budget.model_dump(mode="json"),
        },
        "base_commit": context.base_commit,
        "checks_sha": context.checks_sha,
        "checks_source": context.checks_source,
        "scenario_set": str(context.scenario_set),
        "scenarios": [
            {
                "id": scenario.id,
                "priority": scenario.priority.value,
                "description": scenario.description,
                "weight": scenario.weight,
            }
            for scenario in context.scenarios.scenarios
        ],
        "file_tree": list(context.file_tree),
        "manifests": [{"path": path, "content": text} for path, text in context.manifests],
        "readme": context.readme,
        "memory": list(context.memory),
        "prior_plans": list(context.prior_plans),
        "findings": list(context.findings),
        "budget": {"tokens": context.budget_tokens, "usd": context.budget_usd},
    }
