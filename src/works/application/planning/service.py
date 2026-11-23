"""Plan orchestration: draft, repair, alternatives and compatibility exports."""

from __future__ import annotations

from typing import Protocol

from works.application.planning.context import *  # noqa: F403
from works.application.planning.context import PlannerContext, PlannerOutput
from works.application.planning.deterministic import *  # noqa: F403
from works.application.planning.deterministic import deterministic_proposal, merge_proposal
from works.application.planning.linter import *  # noqa: F403
from works.application.planning.linter import apply_critique, validate_plan
from works.application.planning.store import *  # noqa: F403
from works.application.planning.store import PlanStore, make_plan_version
from works.domain.errors import ConfigError
from works.domain.plan import *  # noqa: F403
from works.domain.plan import (
    PlanCritique,
    PlanMode,
    PlanProvenance,
    PlanStatus,
    PlanVersion,
)
from works.domain.risk import rate_risk


class Planner(Protocol):
    name: str

    async def draft(self, context: PlannerContext) -> PlannerOutput: ...


class Critic(Protocol):
    name: str

    async def review(self, context: PlannerContext, plan: PlanVersion) -> PlanCritique: ...


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
