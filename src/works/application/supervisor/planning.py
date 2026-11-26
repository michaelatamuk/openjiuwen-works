"""Plan drafting, versioning and replanning for one task."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from works.adapters.git.repo import GitRepo
from works.application.execution.quarantine import ensure_outside
from works.application.execution.scenarios import load_scenario_set
from works.application.planning.memory import PlanMemory
from works.application.planning.service import (
    Planner,
    PlannerContext,
    collect_repository_context,
    draft_plan,
    plan_brief,
)
from works.application.reporter import reply_texts
from works.application.run_context import RunContext
from works.domain.errors import (
    ConfigError,
    NotFoundError,
    PolicyError,
)
from works.domain.records import (
    TaskState,
)
from works.domain.trusted import load_trusted_flow

if TYPE_CHECKING:
    from works.application.supervisor.core import Supervisor


def plan_run(sup: Supervisor, task_id: str, *, scenario_set: Path | None = None) -> dict[str, Any]:
    task = sup._queue.load(task_id)
    repo = sup._repo(task)
    base = repo.head()
    trusted = load_trusted_flow(repo, base, task.flow, sup._flows_dir)
    flow = trusted.flow
    payload: dict[str, Any] = {
        "task_id": task.id,
        "flow": flow.flow,
        "product": flow.product,
        "repo": str(repo),
        "state": task.state.value,
        "nodes": [
            {
                "id": node.id,
                "kind": node.kind.value,
                "required": node.required,
                "mode": node.mode.value,
            }
            for node in flow.nodes
        ],
        "base_commit": base,
        "checks_sha": trusted.checks_sha,
        "checks_source": trusted.source,
        "mode": flow.mode.value,
    }
    if scenario_set is not None:
        resolved = scenario_set.expanduser().resolve()
        scenarios = load_scenario_set(resolved)
        ensure_outside(resolved.parent / scenarios.directory, repo.path, label="scenario set")
        payload["scenario_ids"] = [s.id for s in scenarios.scenarios]
    return payload


async def draft_task_plan(sup: Supervisor, task_id: str, *, scenario_set: Path) -> Any:
    """Draft and store a plan without starting a run.

    This is the safe preview used by `works plan`: it does not claim the task, move it to
    planning, or authorize a build. The run drafts its own official version later.
    """
    task = sup._queue.load(task_id)
    repo = sup._repo(task)
    base = repo.head()
    trusted = load_trusted_flow(repo, base, task.flow, sup._flows_dir)
    ctx = RunContext(
        task=task,
        flow=trusted.flow,
        run_id="plan-preview",
        run_dir=sup._paths.runs / "plan-preview",
        worktree=None,
        base_commit=base,
        checks_sha=trusted.checks_sha,
        checks_source=trusted.source,
        plan={},
    )
    await sup._draft_plan(ctx, repo, scenario_set)
    return sup._plans.load(task_id)


async def replan(sup: Supervisor, task_id: str, *, scenario_set: Path | None = None) -> Any:
    """Draft a new plan version without changing the task state.

    Used by `works plan --action replan` and when a planning-state task's base or checks
    changed. The previous version is marked superseded; a person still approves the new one.
    """
    task = sup._queue.load(task_id)
    if task.state not in (TaskState.QUEUED, TaskState.PLANNING):
        raise ConfigError(f"task {task_id} is {task.state.value}; replan from planning")
    repo = sup._repo(task)
    base = repo.head()
    trusted = load_trusted_flow(repo, base, task.flow, sup._flows_dir)
    previous = sup._latest_plan(task_id)
    scenario = scenario_set or (
        Path(previous["scenario_set"]) if previous and previous.get("scenario_set") else None
    )
    if scenario is None:
        raise ConfigError("replan needs a scenario set; pass --scenarios")
    ctx = RunContext(
        task=task,
        flow=trusted.flow,
        run_id="replan",
        run_dir=sup._paths.runs / "replan",
        worktree=None,
        base_commit=base,
        checks_sha=trusted.checks_sha,
        checks_source=trusted.source,
        plan={},
    )
    await sup._draft_plan(ctx, repo, scenario)
    if task.state is TaskState.PLANNING:
        sup._queue.append(task_id, "plan.drafted", ctx.plan)
    if previous and previous.get("plan_id"):
        with contextlib.suppress(NotFoundError):
            sup._plans.mark_superseded(task_id, str(previous["plan_id"]))
    return sup._plans.load(task_id)


async def draft_alternative_plans(
    sup: Supervisor,
    task_id: str,
    *,
    scenario_set: Path,
    planners: dict[str, Planner],
    mode: str,
) -> dict[str, Any]:
    """Draft labelled alternatives without claiming the task or opening a gate."""
    from works.application.planning.service import draft_alternatives

    task = sup._queue.load(task_id)
    repo = sup._repo(task)
    trusted = load_trusted_flow(repo, repo.head(), task.flow, sup._flows_dir)
    ctx = RunContext(
        task=task,
        flow=trusted.flow,
        run_id="alternatives",
        run_dir=sup._paths.runs / "alternatives",
        worktree=None,
        base_commit=repo.head(),
        checks_sha=trusted.checks_sha,
        checks_source=trusted.source,
        plan={},
    )
    context = sup._planner_context(ctx, repo, scenario_set)
    return await draft_alternatives(
        context,
        store=sup._plans,
        mode=mode,
        planners=planners,
        critic=sup._critic,
    )


def _planner_context(
    sup: Supervisor, ctx: RunContext, repo: GitRepo, scenario_set: Path | None
) -> PlannerContext:
    if scenario_set is None:
        raise ConfigError(
            "a scenario set is required: pass --scenarios (at least one P0, written first)"
        )
    resolved = scenario_set.expanduser().resolve()
    scenarios = load_scenario_set(resolved)
    directory = ensure_outside(
        resolved.parent / scenarios.directory, repo.path, label="scenario set"
    )
    ctx.scenario_set = scenarios
    ctx.scenario_dir = directory
    repository = collect_repository_context(repo.path)
    events = sup._queue.events(ctx.task.id)
    findings = tuple(
        str(event.data.get("summary", ""))
        for event in events
        if event.type == "finding" and str(event.data.get("summary", "")).strip()
    )[-5:]
    replies = reply_texts(events)
    return PlannerContext(
        task_id=ctx.task.id,
        product=ctx.task.product,
        task_kind=ctx.task.kind.value,
        source_ref=ctx.task.source.ref,
        source_title=ctx.task.source.title,
        source_text=" ".join(
            item
            for item in (
                ctx.task.source.title,
                ctx.task.source.reproduction_hint or "",
                *replies,
            )
            if item
        ),
        flow=ctx.flow,
        base_commit=repo.head(),
        checks_sha=ctx.checks_sha or "",
        checks_source=ctx.checks_source or "",
        scenario_set=resolved,
        scenarios=scenarios,
        repo=repo.path,
        budget_tokens=ctx.task.budget.tokens,
        budget_usd=ctx.task.budget.usd,
        memory=tuple(ctx.memory_recall),
        prior_plans=tuple(
            PlanMemory(sup._paths).recall(product=ctx.task.product, flow=ctx.flow.flow)
        ),
        findings=findings,
        file_tree=repository.file_tree,
        manifests=repository.manifests,
        readme=repository.readme,
    )


async def _draft_plan(
    sup: Supervisor, ctx: RunContext, repo: GitRepo, scenario_set: Path | None
) -> None:
    context = sup._planner_context(ctx, repo, scenario_set)
    plan = await draft_plan(
        context,
        store=sup._plans,
        mode=sup._planner_mode,
        planner=sup._planner,
        critic=sup._critic,
    )
    ctx.plan = {
        "plan_id": plan.plan_id,
        "version": plan.version,
        "hash": plan.hash,
        "status": plan.status.value,
        "base_commit": plan.base_commit,
        "checks_sha": plan.checks_sha,
        "checks_source": plan.checks_source,
        "scenario_set": plan.scenario_set,
        "scenario_ids": plan.scenario_ids,
        "p0": context.p0_ids,
        "p1": context.p1_ids,
        "nodes": [node.id for node in ctx.flow.nodes],
        "summary": plan.summary,
        "validation": (
            plan.validation.model_dump(mode="json") if plan.validation is not None else None
        ),
        "provenance": plan.provenance.model_dump(mode="json"),
        "brief": plan_brief(plan),
    }
    if plan.validation is not None and not plan.validation.ok:
        raise PolicyError(
            "the plan failed its deterministic lint: " + "; ".join(plan.validation.errors[:4])
        )


def _load_plan_scenarios(sup: Supervisor, ctx: RunContext, repo: GitRepo) -> None:
    if ctx.scenario_set is not None:
        return
    path = Path(ctx.plan["scenario_set"])
    scenarios = load_scenario_set(path)
    directory = ensure_outside(path.parent / scenarios.directory, repo.path, label="scenario set")
    ctx.scenario_set = scenarios
    ctx.scenario_dir = directory


def _latest_plan(sup: Supervisor, task_id: str) -> dict[str, Any] | None:
    plan: dict[str, Any] | None = None
    for event in sup._queue.events(task_id):
        if event.type == "plan.drafted":
            plan = dict(event.data)
    return plan
