"""Deterministic plan lint and critique application."""

from __future__ import annotations

import re
from pathlib import Path

from works.application.planning import preflight
from works.application.planning.context import PlannerContext
from works.domain.plan import PlanCritique, PlanProposal, PlanValidation
from works.domain.policy import check_paths
from works.domain.trusted import is_check_path

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
            errors.append(f"step {step.id or step.node!r} has no done_when")

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

    checks.append("preflight")
    preflight_errors, preflight_warnings = preflight.problems(proposal, context)
    errors.extend(preflight_errors)
    warnings.extend(preflight_warnings)

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


CRITIC_MIN_SCORE = 0.5


def apply_critique(validation: PlanValidation, critique: PlanCritique | None) -> PlanValidation:
    if critique is None:
        return validation
    if critique.allow and critique.score and critique.score < CRITIC_MIN_SCORE:
        return validation.model_copy(
            update={
                "ok": False,
                "errors": [
                    *validation.errors,
                    (
                        f"the critic scored the plan {critique.score:.2f}, "
                        f"below {CRITIC_MIN_SCORE:.2f}"
                    ),
                ],
            }
        )
    if critique.allow:
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
