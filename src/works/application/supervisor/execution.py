"""The run phases: prepare, approve, build, enforce policy, verify and prove."""

from __future__ import annotations

import asyncio
import contextlib
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from works.adapters.git.repo import GitRepo
from works.adapters.harness.base import Proposal
from works.adapters.processes.runner import CommandResult
from works.application.execution.artifacts import collect_artifacts
from works.application.planning.memory import PlanMemory
from works.application.planning.service import (
    plan_deviations,
)
from works.application.reproduce import detect, env
from works.application.reproduce.classify import is_setup_failure
from works.application.run_context import RunContext, _required
from works.domain.errors import (
    ConfigError,
    NotFoundError,
    StateError,
)
from works.domain.flow import GateMode, Node, NodeKind
from works.domain.policy import PolicyReport, Violation, check_patch, check_paths, paths_from_patch
from works.domain.records import (
    StopReason,
    TaskKind,
    TaskState,
)
from works.domain.risk import rate_risk
from works.domain.trusted import is_check_path

if TYPE_CHECKING:
    from works.application.supervisor.core import Supervisor


async def _execute(
    sup: Supervisor,
    ctx: RunContext,
    repo: GitRepo,
    approve_plan: bool,
    scenario_set: Path | None,
) -> None:
    if not await sup._prepare(ctx, repo, scenario_set):
        return
    if not sup._approve_plan(ctx, repo, approve_plan):
        return
    touched = await sup._build(ctx, repo)
    if touched is None:
        return
    proposal = _required(ctx.proposal, "proposal")
    if not sup._enforce_policy(ctx, repo, proposal, touched):
        return
    if not await sup._verify(ctx, proposal):
        return
    sup._prove(ctx)


async def _prepare(
    sup: Supervisor, ctx: RunContext, repo: GitRepo, scenario_set: Path | None
) -> bool:
    """Reproduce the defect and draft the plan. False means the run stops here."""
    flow = ctx.flow
    task = ctx.task
    if task.state is TaskState.QUEUED:
        sup._move(ctx, TaskState.REPRODUCING)
        ctx.base_commit = ctx.base_commit or repo.head()
        ctx.worktree = sup._prepare_worktree(ctx, repo, ctx.base_commit)
        ctx.reproduction = detect.choose(
            Path(task.repo or repo.path), task.source.reproduction_hint
        )
        ctx.reproduction_env = env.fingerprint(sup._paths, repo.path)
        node = flow.node("reproduce")
        if task.reproduction_command:
            node = node.model_copy(
                update={
                    "cmd": shlex.join(task.reproduction_command),
                    "kind": NodeKind.DETERMINISTIC,
                }
            )
        reproduce = await sup._run_node(ctx, "reproduce", node)
        if not reproduce.ok:
            if is_setup_failure(reproduce.output):
                ctx.reproduction_stable = False
                sup._stop(
                    ctx,
                    StopReason.CONFIG_ERROR,
                    detail="the reproduction failed on missing dependencies or a missing command",
                )
                return False
            again = await sup._run_node(ctx, "reproduce", node)
            ctx.reproduction_attempts = 2
            if again.ok:
                ctx.reproduction_stable = False
                sup._stop(
                    ctx,
                    StopReason.FLAKY_TEST,
                    detail="the reproduction failed once and passed on a second run",
                )
                return False
            reproduce = again
        ctx.reproduce = reproduce.record("reproduce")
        if reproduce.ok:
            ctx.state = TaskState.REPRODUCING
            sup._stop(ctx, StopReason.NOT_REPRODUCIBLE)
            return False
        sup._move(ctx, TaskState.REPRODUCED)
        sup._recall_memory(ctx)
        await sup._draft_plan(ctx, repo, scenario_set)
        sup._move(ctx, TaskState.PLANNING)
        sup._queue.append(task.id, "plan.drafted", ctx.plan)
    else:
        if not ctx.plan:
            raise StateError(f"cannot resume {task.state.value} without a plan")
        stored = Path(ctx.plan["scenario_set"])
        scenario_set = scenario_set or stored
        ctx.worktree = sup._prepare_worktree(ctx, repo, _required(ctx.base_commit, "base commit"))
    return True


def _approve_plan(sup: Supervisor, ctx: RunContext, repo: GitRepo, approve_plan: bool) -> bool:
    """Check the plan gate. False means the plan is not approved yet."""
    gate = ctx.flow.gate("plan")
    current = sup._current_state(ctx)
    already_approved = current is TaskState.PLAN_APPROVED
    if already_approved:
        sup._require_approval(ctx, "plan")
    decision = sup._decide(ctx, "plan", already_approved=already_approved)
    if (
        decision.source == "laix"
        and decision.action == "allow"
        and not approve_plan
        and not already_approved
    ):
        approve_plan = True
    if not approve_plan and not already_approved and gate.action != "allow":
        sup._stop(ctx, StopReason.NEEDS_PLAN_APPROVAL)
        return False
    if current is TaskState.PLANNING:
        sup._move(ctx, TaskState.PLAN_APPROVED)
        approver = "cli" if approve_plan else "flow"
        if ctx.plan.get("plan_id") and ctx.plan.get("hash"):
            with contextlib.suppress(NotFoundError):
                approved_plan = sup._plans.approve(
                    ctx.task.id,
                    plan_id=str(ctx.plan["plan_id"]),
                    plan_hash=str(ctx.plan["hash"]),
                    by=approver,
                )
                PlanMemory(sup._paths).remember(approved_plan, by=approver)
        sup._queue.append(
            ctx.task.id,
            "gate.decided",
            {
                "gate": "plan",
                "decision": "approved",
                "by": approver,
                "commit": ctx.base_commit,
                "checks_sha": ctx.checks_sha,
                "risk": ctx.risk.level.value if ctx.risk is not None else None,
                "owners": ctx.risk.owners if ctx.risk is not None else [],
                "required_reviewers": (ctx.risk.required_reviewers if ctx.risk is not None else 1),
                "plan_id": ctx.plan.get("plan_id"),
                "plan_hash": ctx.plan.get("hash"),
            },
        )
    if not ctx.plan:
        raise ConfigError("no scenario set was provided for the run")
    sup._load_plan_scenarios(ctx, repo)
    return True


async def _build(sup: Supervisor, ctx: RunContext, repo: GitRepo) -> list[str] | None:
    """One builder turn, then risk and plan drift. None means the run stops."""
    flow = ctx.flow
    task = ctx.task
    sup._move(ctx, TaskState.BUILDING)
    proposal = await sup._propose(ctx)
    if proposal is None:
        return None
    ctx.proposal = proposal
    if proposal.tokens > task.budget.tokens or proposal.usd > task.budget.usd:
        sup._stop(ctx, StopReason.BUDGET_EXCEEDED)
        return None
    if sup._over_wall(ctx):
        sup._stop(ctx, StopReason.BUDGET_EXCEEDED, detail="wall-clock budget")
        return None
    from works.application.limits import check as check_daily
    from works.domain.errors import BudgetError

    try:
        check_daily(sup._paths, add_usd=proposal.usd)
    except BudgetError as exc:
        sup._stop(ctx, StopReason.BUDGET_EXCEEDED, detail=str(exc))
        return None
    worktree = _required(ctx.worktree, "worktree")
    touched = proposal.touched_paths or (
        repo.all_changed_files(worktree) if proposal.applied else paths_from_patch(proposal.patch)
    )
    stats = repo.diff_stat(worktree) if proposal.applied else []
    ctx.risk = rate_risk(paths=touched, diff_stat=stats, flow=flow)
    sup._queue.append(
        ctx.task.id,
        "risk.rated",
        ctx.risk.model_dump(mode="json"),
    )
    if ctx.plan.get("plan_id") and ctx.plan.get("version"):
        with contextlib.suppress(NotFoundError):
            plan_version = sup._plans.load(ctx.task.id, int(ctx.plan["version"]))
            deviations = plan_deviations(plan_version, touched)
            if deviations:
                ctx.plan_deviations = deviations
                sup._queue.append(
                    ctx.task.id,
                    "plan.deviation",
                    {
                        "plan_id": plan_version.plan_id,
                        "planned": sorted(
                            {path for step in plan_version.steps for path in step.files}
                        ),
                        "touched": touched,
                        "deviations": deviations,
                    },
                )
    if flow.risk.mode is GateMode.OBSERVE and ctx.risk.required_reviewers > 1:
        sup._observe(
            ctx,
            "risk",
            [f"{ctx.risk.level.value} risk would require {ctx.risk.required_reviewers} reviewers"],
        )
    return touched


def _enforce_policy(
    sup: Supervisor, ctx: RunContext, repo: GitRepo, proposal: Proposal, touched: list[str]
) -> bool:
    """Check touched paths against the flow. False means the change is refused."""
    flow = ctx.flow
    worktree = _required(ctx.worktree, "worktree")
    check_touched = [path for path in touched if is_check_path(path)]
    if check_touched and ctx.task.kind is not TaskKind.CHECK_CHANGE:
        ctx.policy = PolicyReport(
            ok=False,
            violations=[
                Violation(
                    path=path,
                    reason="check change requires a check-change task",
                )
                for path in check_touched
            ],
        )
        sup._stop(ctx, StopReason.POLICY_VIOLATION)
        return False
    violations = (
        check_paths(touched, flow.paths)
        if proposal.applied
        else check_patch(proposal.patch, flow.paths)
    )
    ctx.policy = PolicyReport(ok=not violations, violations=violations)
    if violations:
        if flow.mode is GateMode.OBSERVE:
            sup._observe(ctx, "policy", [v.reason for v in violations])
        else:
            sup._stop(ctx, StopReason.POLICY_VIOLATION)
            return False
    if not proposal.applied:
        repo.apply_patch(worktree, proposal.patch, ctx.run_dir / "proposal.diff")
    return True


async def _verify(sup: Supervisor, ctx: RunContext, proposal: Proposal) -> bool:
    """Preview, test, challenge and judge the change. False stops the run."""
    flow = ctx.flow
    sup._move(ctx, TaskState.CHECKING)
    if any(node.id == "preview" for node in flow.nodes):
        preview_node = flow.node("preview")
        if preview_node.mode is not GateMode.OFF:
            preview = await sup._run_node(ctx, "preview", preview_node)
            ctx.preview = preview.record("preview")
            if not preview.ok:
                if preview_node.mode is GateMode.OBSERVE:
                    sup._observe(ctx, "preview", [f"exit {preview.exit_code}"])
                else:
                    sup._stop(ctx, StopReason.TESTS_FAILED, detail="preview failed")
                    return False
    if any(node.id == "preview" for node in flow.nodes) and ctx.worktree is not None:
        ctx.artifacts = collect_artifacts(
            ctx.worktree / ".works" / "artifacts",
            ctx.run_dir / "artifacts",
        )
    if any(node.id == "test" for node in flow.nodes):
        test_node = flow.node("test")
        if test_node.mode is not GateMode.OFF:
            test = await sup._run_node(ctx, "test", test_node)
            ctx.test = test.record("test")
            if not test.ok:
                if test_node.mode is GateMode.OBSERVE:
                    sup._observe(ctx, "test", [f"exit {test.exit_code}"])
                else:
                    sup._stop(ctx, StopReason.TESTS_FAILED)
                    return False
            if sup._over_wall(ctx):
                sup._stop(ctx, StopReason.BUDGET_EXCEEDED, detail="wall-clock budget")
                return False
    if any(node.id == "challenge" for node in flow.nodes):
        challenge_node = flow.node("challenge")
        if challenge_node.mode is not GateMode.OFF:
            challenge = await sup._challenge(ctx, proposal)
            ctx.challenge = challenge
            if not challenge.allow:
                if challenge_node.mode is GateMode.OBSERVE:
                    sup._observe(ctx, "challenge", [challenge.reason])
                else:
                    sup._stop(ctx, StopReason.CHALLENGE_FAILED, detail=challenge.reason)
                    return False
    if not sup._check_flakes(ctx):
        return False
    verdict = await sup._judge(ctx)
    ctx.verdict = verdict
    (ctx.run_dir / "verdict.json").write_text(
        verdict.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    if not verdict.allow:
        sup._stop(ctx, StopReason.VERDICT_FAILED)
        return False
    return True


def _prove(sup: Supervisor, ctx: RunContext) -> None:
    sup._move(ctx, TaskState.PROVED)
    sup._decide(ctx, "release")
    sup._queue.append(
        ctx.task.id,
        "note",
        {"message": "proof is ready; gate 2 is the next step"},
    )
    ctx.stop_reason = StopReason.COMPLETED


def _prepare_worktree(sup: Supervisor, ctx: RunContext, repo: GitRepo, base: str) -> Path:
    repo.require_clean()
    destination = sup._paths.worktrees / ctx.run_id / "repo"
    if destination.exists():
        repo.worktree_remove(destination)
    repo.worktree_add(destination, base)
    sup._queue.append(ctx.task.id, "step.started", {"step": "worktree", "base": base})
    return destination


def _recall_memory(sup: Supervisor, ctx: RunContext) -> None:
    recall = getattr(sup._memory, "recall", None)
    if not callable(recall):
        return
    try:
        statements = [str(item) for item in recall(limit=5)]
    except Exception as exc:
        sup._queue.append(
            ctx.task.id,
            "memory.recall_failed",
            {"error": str(exc)[:500]},
        )
        return
    if not statements:
        return
    ctx.memory_recall = statements
    sup._queue.append(
        ctx.task.id,
        "memory.recalled",
        {"view": "about_me", "statements": statements},
    )


async def _run_node(sup: Supervisor, ctx: RunContext, step: str, node: Node) -> CommandResult:
    worktree = _required(ctx.worktree, "worktree")
    sup._queue.append(ctx.task.id, "step.started", {"step": step})
    result = await asyncio.to_thread(
        sup._verifier.run,
        node.argv(sup.python),
        worktree,
        env={"PYTHONPATH": str(worktree)},
        timeout_s=node.timeout_s,
    )
    record = result.record(step)
    ctx.commands.append(record)
    sup._queue.append(ctx.task.id, "step.finished", {"step": step, "exit_code": result.exit_code})
    return result
