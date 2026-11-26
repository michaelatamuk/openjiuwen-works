"""Builder turns, scenario runs, gates and observe-mode handling."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from works.adapters.harness.base import Proposal, ProposalRequest, ReviewRequest
from works.application.approvals.decisions import (
    GateContext,
    GateVerdict,
    ShadowGate,
)
from works.application.execution.flakes import active_flakes
from works.application.execution.scenarios import Scenario, judge
from works.application.run_context import RunContext, _required
from works.domain.errors import (
    ConfigError,
    ConflictError,
    HarnessError,
    StateError,
)
from works.domain.flow import FlowSpec, GateMode
from works.domain.policy import matches, paths_from_patch
from works.domain.records import (
    Challenge,
    ScenarioOutcome,
    StopReason,
    Verdict,
)
from works.domain.review import SpecialistReview
from works.domain.risk import RiskLevel

if TYPE_CHECKING:
    from works.application.supervisor.core import Supervisor


async def _propose(sup: Supervisor, ctx: RunContext) -> Proposal | None:
    worktree = _required(ctx.worktree, "worktree")
    base_commit = _required(ctx.base_commit, "base commit")
    if sup._harness is None:
        raise ConfigError("no harness configured: pass --trace PATH (the live adapter lands in M1)")
    sup._queue.append(ctx.task.id, "attempt.started", {"attempt": ctx.task.attempts + 1})
    request = ProposalRequest(
        task_id=ctx.task.id,
        source_ref=ctx.task.source.ref,
        title=ctx.task.source.title,
        worktree=worktree,
        base_commit=base_commit,
        plan=ctx.plan,
    )
    try:
        proposal = await sup._harness.propose(request)
    except HarnessError as exc:
        sup._stop(ctx, StopReason.HARNESS_FAILED, detail=str(exc))
        return None
    (ctx.run_dir / "harness.json").write_text(
        proposal.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    if proposal.stop:
        ctx.proposal = proposal
        sup._stop(ctx, StopReason.HARNESS_FAILED, detail=proposal.stop)
        return None
    sup._queue.append(
        ctx.task.id,
        "note",
        {
            "message": "proposal received",
            "model": proposal.model,
            "provider": proposal.provider,
            "tokens": proposal.tokens,
            "usd": proposal.usd,
            "paths": paths_from_patch(proposal.patch),
        },
    )
    return proposal


async def _challenge(sup: Supervisor, ctx: RunContext, proposal: Proposal) -> Challenge:
    if sup._harness is None:
        raise ConfigError("the flow asks for a challenge but no harness is configured")
    worktree = _required(ctx.worktree, "worktree")
    base_commit = _required(ctx.base_commit, "base commit")
    request = ProposalRequest(
        task_id=ctx.task.id,
        source_ref=ctx.task.source.ref,
        title=ctx.task.source.title,
        worktree=worktree,
        base_commit=base_commit,
        plan=ctx.plan,
    )
    return await sup._harness.challenge(request, proposal)


def record_challenge(sup: Supervisor, ctx: RunContext, challenge: Challenge) -> None:
    (ctx.run_dir / "challenge.json").write_text(
        challenge.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    sup._queue.append(
        ctx.task.id,
        "challenge.decided",
        challenge.model_dump(mode="json"),
    )


def specialists_for(flow: FlowSpec, paths: list[str]) -> list[tuple[str, list[str]]]:
    """The configured specialists whose paths this change actually touches."""
    if flow.review.mode is GateMode.OFF:
        return []
    selected: list[tuple[str, list[str]]] = []
    for area, patterns in flow.review.specialists.items():
        hits = sorted({path for path in paths if matches(path, patterns)})
        if hits:
            selected.append((area, hits))
    return selected


async def _specialists(
    sup: Supervisor, ctx: RunContext, proposal: Proposal, challenge: Challenge
) -> Challenge:
    paths = proposal.touched_paths or paths_from_patch(proposal.patch)
    selected = specialists_for(ctx.flow, paths)
    if not selected:
        return challenge
    harness = sup._harness
    if harness is None:
        raise ConfigError("specialist reviews need a harness")
    if not getattr(harness, "supports_reviews", False):
        raise ConfigError("the configured harness does not support specialist reviews")
    worktree = _required(ctx.worktree, "worktree")
    base_commit = _required(ctx.base_commit, "base commit")
    mode = ctx.flow.review.mode

    async def one(area: str, focus: list[str]) -> SpecialistReview:
        request = ProposalRequest(
            task_id=ctx.task.id,
            source_ref=ctx.task.source.ref,
            title=ctx.task.source.title,
            worktree=worktree,
            base_commit=base_commit,
            plan=ctx.plan,
            review=ReviewRequest(area=area, focus=focus, mode=mode.value),
        )
        try:
            verdict = await harness.challenge(request, proposal)
        except HarnessError as exc:
            return SpecialistReview(
                area=area,
                allow=False,
                reason=f"reviewer could not run: {exc}",
            )
        return SpecialistReview(
            area=area,
            allow=verdict.allow,
            reason=verdict.reason,
            concerns=list(verdict.concerns),
            model=verdict.model,
            provider=verdict.provider,
            tokens=verdict.tokens,
            usd=verdict.usd,
            prompt_sha256=verdict.prompt_sha256,
        )

    reviews = list(await asyncio.gather(*(one(area, focus) for area, focus in selected)))
    ctx.specialists = reviews
    (ctx.run_dir / "specialists.json").write_text(
        "\n".join(review.model_dump_json(indent=2) for review in reviews) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    for review in reviews:
        sup._queue.append(ctx.task.id, "specialist.reviewed", review.model_dump(mode="json"))
    if mode is GateMode.ENFORCE:
        blocked = [review for review in reviews if not review.allow]
        if blocked:
            reason = "; ".join(f"{item.area}: {item.reason}" for item in blocked)
            concerns = [
                *challenge.concerns,
                *(f"{item.area}: {text}" for item in blocked for text in item.concerns),
            ]
            challenge = challenge.model_copy(
                update={
                    "allow": False,
                    "reason": f"specialist blocked ? {reason}",
                    "concerns": concerns,
                }
            )
    return challenge


def repeats() -> int:
    raw = os.environ.get("WORKS_REPEAT_SCENARIOS", "1")
    try:
        value = int(raw)
    except ValueError:
        return 1
    return max(1, min(3, value))


async def _judge(sup: Supervisor, ctx: RunContext) -> Verdict:
    scenario_set = _required(ctx.scenario_set, "scenario set")
    _required(ctx.scenario_dir, "scenario directory")
    _required(ctx.worktree, "worktree")
    count = repeats()

    async def once(scenario: Scenario) -> tuple[ScenarioOutcome, bool]:
        results = [await sup._run_scenario(ctx, scenario) for _ in range(count)]
        mixed = any(result.passed != results[0].passed for result in results)
        if mixed:
            failed = results[0].model_copy(update={"passed": False, "exit_code": -1})
            return failed, True
        return results[0], False

    tasks: list[tuple[Scenario, asyncio.Task[tuple[ScenarioOutcome, bool]]]] = []
    async with asyncio.TaskGroup() as group:
        for scenario in scenario_set.scenarios:
            tasks.append((scenario, group.create_task(once(scenario))))
    outcomes = [task.result()[0] for _, task in tasks]
    unstable = [scenario.id for scenario, task in tasks if task.result()[1]]
    if unstable:
        sup._stop(
            ctx,
            StopReason.FLAKY_TEST,
            detail=f"unstable scenario(s) across {count} runs: {', '.join(unstable)}",
        )
    return judge(outcomes, run_id=ctx.run_id)


def _check_flakes(sup: Supervisor, ctx: RunContext) -> bool:
    scenario_set = _required(ctx.scenario_set, "scenario set")
    ids = {scenario.id for scenario in scenario_set.scenarios}
    hits = [
        flake
        for flake in active_flakes(sup._paths, task_id=ctx.task.id)
        if flake.scenario_id in ids
    ]
    if not hits:
        return True
    for flake in hits:
        sup._queue.append(ctx.task.id, "flake", flake.model_dump(mode="json"))
    detail = ", ".join(f"{flake.scenario_id} ({flake.owner})" for flake in hits)
    sup._stop(ctx, StopReason.FLAKY_TEST, detail=f"active flake: {detail}")
    return False


async def _run_scenario(sup: Supervisor, ctx: RunContext, scenario: Scenario) -> ScenarioOutcome:
    worktree = _required(ctx.worktree, "worktree")
    scenario_dir = _required(ctx.scenario_dir, "scenario directory")
    argv = scenario.argv(sup.python, scenario_dir)
    result = await asyncio.to_thread(
        sup._verifier.run,
        argv,
        worktree,
        env={"PYTHONPATH": str(worktree)},
        timeout_s=scenario.timeout_s,
    )
    return ScenarioOutcome(
        id=scenario.id,
        priority=scenario.priority,
        weight=scenario.weight,
        passed=result.ok,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        output_sha256=result.output_sha256,
    )


def _observe(sup: Supervisor, ctx: RunContext, gate: str, reasons: list[str]) -> None:
    detail = "; ".join(reasons) or "blocked"
    ctx.would_block.append(f"{gate}: {detail}")
    sup._queue.append(
        ctx.task.id,
        "would_block",
        {"gate": gate, "reason": detail, "mode": GateMode.OBSERVE.value},
    )


def _decide(
    sup: Supervisor, ctx: RunContext, gate: str, *, already_approved: bool = False
) -> GateVerdict:
    evidence: list[str] = []
    if ctx.reproduce is not None:
        evidence.append("the reproduction failed on the base commit")
    if ctx.verdict is not None:
        evidence.append(f"the verifier verdict is {'allow' if ctx.verdict.allow else 'block'}")
    if ctx.challenge is not None:
        evidence.append(f"the challenger verdict is {'allow' if ctx.challenge.allow else 'block'}")
    if ctx.risk is not None:
        evidence.append(f"the risk rating is {ctx.risk.level.value}")
    if ctx.plan:
        evidence.append(f"the plan names {len(ctx.plan.get('scenario_ids', []))} scenarios")
    context = GateContext(
        task_id=ctx.task.id,
        gate=gate,
        base_commit=ctx.base_commit,
        risk=ctx.risk.level if ctx.risk is not None else RiskLevel.MEDIUM,
        required_reviewers=ctx.risk.required_reviewers if ctx.risk is not None else 1,
        owners=ctx.risk.owners if ctx.risk is not None else [],
        policy_ok=ctx.policy.ok,
        verdict_allow=None if ctx.verdict is None else ctx.verdict.allow,
        challenge_allow=None if ctx.challenge is None else ctx.challenge.allow,
        already_approved=already_approved,
        touched_paths=[],
        diff_lines=ctx.risk.lines if ctx.risk is not None else 0,
        budget_usd_left=ctx.task.budget.usd,
        evidence=evidence,
    )
    verdict = sup._decision.decide(context)
    ctx.decisions.append(verdict)
    payload = {"gate": gate, "mode": sup._decision.mode, **verdict.model_dump(mode="json")}
    sup._queue.append(ctx.task.id, "decision.made", payload)
    if isinstance(sup._decision, ShadowGate):
        shadow = sup._decision.last_shadow
        sup._queue.append(
            ctx.task.id,
            "decision.shadow",
            {
                "gate": gate,
                "agree": None if shadow is None else verdict.action == shadow.action,
                "shadow": None if shadow is None else shadow.model_dump(mode="json"),
                "error": sup._decision.last_error,
            },
        )
    return verdict


def _require_approval(sup: Supervisor, ctx: RunContext, gate: str) -> None:
    decisions = [
        event
        for event in sup._queue.events(ctx.task.id)
        if event.type == "gate.decided" and event.data.get("gate") == gate
    ]
    if not decisions:
        raise StateError(f"task is {ctx.state.value} but has no {gate} approval")
    last = decisions[-1].data
    if last.get("commit") != ctx.base_commit:
        raise ConflictError(
            f"the {gate} approval is bound to {last.get('commit')}, "
            f"not {ctx.base_commit}; approve the current commit"
        )
    if last.get("checks_sha") not in (None, ctx.checks_sha):
        raise ConflictError(f"the checks changed since the {gate} approval; approve again")
    approved_plan = last.get("plan_hash")
    current_plan = ctx.plan.get("hash")
    if approved_plan and current_plan and approved_plan != current_plan:
        raise ConflictError("the plan changed since approval; approve the current version")


def _over_wall(sup: Supervisor, ctx: RunContext) -> bool:
    elapsed_minutes = (sup._clock() - ctx.started_at).total_seconds() / 60
    return elapsed_minutes > ctx.task.budget.wall_minutes
