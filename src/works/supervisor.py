"""The supervisor owns the loop. CLI commands only call it; they never act on their own."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .artifacts import collect_artifacts
from .config import WorksPaths
from .decision import DecisionPort, GateContext, GateVerdict, ShadowGate, build_decision_port
from .errors import ConfigError, ConflictError, HarnessError, StateError, WorksError
from .evidence import Artifact, DiffStatRow, Evidence, write_evidence
from .flakes import active_flakes
from .flow import FlowSpec, GateMode, Node, PathsSpec
from .gitops import GitRepo
from .harness.base import Harness, Proposal, ProposalRequest
from .ledger import Ledger
from .logs import get_logger
from .memory import Memory, NullMemory
from .policy import PolicyReport, Violation, check_patch, check_paths, paths_from_patch
from .quarantine import ensure_outside
from .quarantine import load as load_quarantine
from .queue import Queue
from .records import (
    Challenge,
    CommandRecord,
    Finding,
    LedgerRow,
    RunRecord,
    ScenarioOutcome,
    StopReason,
    Task,
    TaskKind,
    TaskState,
    Verdict,
)
from .risk import RiskLevel, RiskRating, rate_risk
from .runner import CommandResult, CommandRunner
from .scenarios import Scenario, ScenarioSet, judge, load_scenario_set
from .state import TERMINAL
from .trusted import is_check_path, load_trusted_flow
from .verifier import LocalVerifier, Verifier

LOG = get_logger("supervisor")


def new_run_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(tz=UTC)).strftime("%Y%m%dT%H%M%S")
    return f"r-{stamp}-{secrets.token_hex(3)}"


def _required[T](value: T | None, what: str) -> T:
    if value is None:
        raise StateError(f"{what} is not set; the run cannot continue")
    return value


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
    test: CommandRecord | None = None
    preview: CommandRecord | None = None
    artifacts: list[Artifact] = field(default_factory=list)
    memory_recall: list[str] = field(default_factory=list)
    proposal: Proposal | None = None
    verdict: Verdict | None = None
    challenge: Challenge | None = None
    policy: PolicyReport = field(default_factory=lambda: PolicyReport(ok=True))
    risk: RiskRating | None = None
    decisions: list[GateVerdict] = field(default_factory=list)
    would_block: list[str] = field(default_factory=list)
    plan: dict[str, Any] = field(default_factory=dict)
    scenario_set: ScenarioSet | None = None
    scenario_dir: Path | None = None
    state: TaskState = TaskState.QUEUED
    stop_reason: StopReason = StopReason.COMPLETED
    error: str | None = None


class Supervisor:
    def __init__(
        self,
        *,
        paths: WorksPaths,
        queue: Queue,
        ledger: Ledger,
        harness: Harness | None,
        runner: CommandRunner,
        memory: Memory | None = None,
        flows_dir: Path | None = None,
        python: str | None = None,
        clock: Callable[[], datetime] | None = None,
        decision_mode: str | None = None,
        decision_port: DecisionPort | None = None,
        verifier: Verifier | None = None,
    ) -> None:
        self._paths = paths
        self._queue = queue
        self._ledger = ledger
        self._harness = harness
        self._runner = runner
        self._memory = memory or NullMemory()
        self._flows_dir = flows_dir or paths.flows
        self._python = python
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._decision_mode = decision_mode
        self._decision: DecisionPort = decision_port or build_decision_port(decision_mode)
        self._verifier: Verifier = verifier or LocalVerifier(runner)

    @property
    def python(self) -> str:
        if self._python:
            return self._python
        import sys

        return sys.executable

    def plan_run(self, task_id: str, *, scenario_set: Path | None = None) -> dict[str, Any]:
        task = self._queue.load(task_id)
        repo = self._repo(task)
        base = repo.head()
        trusted = load_trusted_flow(repo, base, task.flow, self._flows_dir)
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

    async def run(
        self,
        task_id: str,
        *,
        approve_plan: bool = False,
        scenario_set: Path | None = None,
        quarantine: Path | None = None,
    ) -> RunRecord:
        task = self._queue.load(task_id)
        if task.state in TERMINAL:
            raise StateError(
                f"task {task_id} is {task.state.value}; a terminal task cannot be run again"
            )
        if task.state not in (TaskState.QUEUED, TaskState.PLANNING, TaskState.PLAN_APPROVED):
            raise StateError(
                f"task {task_id} is {task.state.value}; resume from this state lands in M1"
            )
        repo = self._repo(task)
        plan = self._latest_plan(task.id) if task.state is not TaskState.QUEUED else None
        if task.state is not TaskState.QUEUED and plan is None:
            raise StateError(f"cannot resume {task.state.value} without a plan")
        base = str(plan["base_commit"]) if plan is not None else repo.head()
        trusted = load_trusted_flow(repo, base, task.flow, self._flows_dir)
        flow = trusted.flow
        if plan is not None:
            planned_sha = plan.get("checks_sha")
            if planned_sha and planned_sha != trusted.checks_sha:
                raise ConflictError(
                    "the checks changed since the plan was drafted; re-plan before building"
                )
        if quarantine is not None:
            flow = self._apply_quarantine(flow, quarantine, repo)
        run_id = new_run_id()
        run_dir = self._paths.run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        self._queue.claim(task_id, run_id)
        ctx = RunContext(
            task=task,
            flow=flow,
            run_id=run_id,
            run_dir=run_dir,
            worktree=None,
            base_commit=base,
            checks_sha=trusted.checks_sha,
            checks_source=trusted.source,
            state=task.state,
            started_at=self._clock(),
            plan=plan or {},
        )
        try:
            await self._execute(ctx, repo, approve_plan, scenario_set)
        except WorksError as exc:
            LOG.warning("run stopped: %s", exc, extra={"run_id": run_id, "task_id": task_id})
            self._abort(ctx, str(exc), reason=self._reason_for(exc))
        except Exception as exc:
            LOG.exception("unexpected failure", extra={"run_id": run_id, "task_id": task_id})
            self._abort(ctx, f"internal error: {exc}")
        finally:
            try:
                record = self._finish(ctx, repo)
            finally:
                self._queue.release(task_id, run_id)
        return record

    async def _execute(
        self,
        ctx: RunContext,
        repo: GitRepo,
        approve_plan: bool,
        scenario_set: Path | None,
    ) -> None:
        flow = ctx.flow
        task = ctx.task
        if task.state is TaskState.QUEUED:
            self._move(ctx, TaskState.REPRODUCING)
            ctx.base_commit = ctx.base_commit or repo.head()
            ctx.worktree = self._prepare_worktree(ctx, repo, ctx.base_commit)
            reproduce = await self._run_node(ctx, "reproduce", flow.node("reproduce"))
            ctx.reproduce = reproduce.record("reproduce")
            if reproduce.ok:
                ctx.state = TaskState.REPRODUCING
                self._stop(ctx, StopReason.NOT_REPRODUCIBLE)
                return
            self._move(ctx, TaskState.REPRODUCED)
            self._recall_memory(ctx)
            self._draft_plan(ctx, repo, scenario_set)
            self._move(ctx, TaskState.PLANNING)
            self._queue.append(task.id, "plan.drafted", ctx.plan)
        else:
            if not ctx.plan:
                raise StateError(f"cannot resume {task.state.value} without a plan")
            stored = Path(ctx.plan["scenario_set"])
            scenario_set = scenario_set or stored
            ctx.worktree = self._prepare_worktree(
                ctx, repo, _required(ctx.base_commit, "base commit")
            )

        gate = flow.gate("plan")
        current = self._current_state(ctx)
        already_approved = current is TaskState.PLAN_APPROVED
        if already_approved:
            self._require_approval(ctx, "plan")
        decision = self._decide(ctx, "plan", already_approved=already_approved)
        if (
            decision.source == "laix"
            and decision.action == "allow"
            and not approve_plan
            and not already_approved
        ):
            approve_plan = True
        if not approve_plan and not already_approved and gate.action != "allow":
            self._stop(ctx, StopReason.NEEDS_PLAN_APPROVAL)
            return
        if current is TaskState.PLANNING:
            self._move(ctx, TaskState.PLAN_APPROVED)
            self._queue.append(
                ctx.task.id,
                "gate.decided",
                {
                    "gate": "plan",
                    "decision": "approved",
                    "by": "cli" if approve_plan else "flow",
                    "commit": ctx.base_commit,
                    "checks_sha": ctx.checks_sha,
                    "risk": ctx.risk.level.value if ctx.risk is not None else None,
                    "owners": ctx.risk.owners if ctx.risk is not None else [],
                    "required_reviewers": (
                        ctx.risk.required_reviewers if ctx.risk is not None else 1
                    ),
                },
            )

        if not ctx.plan:
            raise ConfigError("no scenario set was provided for the run")
        self._load_plan_scenarios(ctx, repo)

        self._move(ctx, TaskState.BUILDING)
        proposal = await self._propose(ctx)
        if proposal is None:
            return
        ctx.proposal = proposal

        if proposal.tokens > task.budget.tokens or proposal.usd > task.budget.usd:
            self._stop(ctx, StopReason.BUDGET_EXCEEDED)
            return
        if self._over_wall(ctx):
            self._stop(ctx, StopReason.BUDGET_EXCEEDED, detail="wall-clock budget")
            return

        worktree = _required(ctx.worktree, "worktree")
        touched = proposal.touched_paths or (
            repo.all_changed_files(worktree)
            if proposal.applied
            else paths_from_patch(proposal.patch)
        )
        stats = repo.diff_stat(worktree) if proposal.applied else []
        ctx.risk = rate_risk(paths=touched, diff_stat=stats, flow=flow)
        self._queue.append(
            ctx.task.id,
            "risk.rated",
            ctx.risk.model_dump(mode="json"),
        )
        if flow.risk.mode is GateMode.OBSERVE and ctx.risk.required_reviewers > 1:
            self._observe(
                ctx,
                "risk",
                [
                    f"{ctx.risk.level.value} risk would require "
                    f"{ctx.risk.required_reviewers} reviewers"
                ],
            )

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
            self._stop(ctx, StopReason.POLICY_VIOLATION)
            return

        violations = (
            check_paths(touched, flow.paths)
            if proposal.applied
            else check_patch(proposal.patch, flow.paths)
        )
        ctx.policy = PolicyReport(ok=not violations, violations=violations)
        if violations:
            if flow.mode is GateMode.OBSERVE:
                self._observe(ctx, "policy", [v.reason for v in violations])
            else:
                self._stop(ctx, StopReason.POLICY_VIOLATION)
                return

        if not proposal.applied:
            repo.apply_patch(worktree, proposal.patch, ctx.run_dir / "proposal.diff")
        self._move(ctx, TaskState.CHECKING)

        if any(node.id == "preview" for node in flow.nodes):
            preview_node = flow.node("preview")
            if preview_node.mode is not GateMode.OFF:
                preview = await self._run_node(ctx, "preview", preview_node)
                ctx.preview = preview.record("preview")
                if not preview.ok:
                    if preview_node.mode is GateMode.OBSERVE:
                        self._observe(ctx, "preview", [f"exit {preview.exit_code}"])
                    else:
                        self._stop(ctx, StopReason.TESTS_FAILED, detail="preview failed")
                        return

        if any(node.id == "preview" for node in flow.nodes) and ctx.worktree is not None:
            ctx.artifacts = collect_artifacts(
                ctx.worktree / ".works" / "artifacts",
                ctx.run_dir / "artifacts",
            )

        if any(node.id == "test" for node in flow.nodes):
            test_node = flow.node("test")
            if test_node.mode is not GateMode.OFF:
                test = await self._run_node(ctx, "test", test_node)
                ctx.test = test.record("test")
                if not test.ok:
                    if test_node.mode is GateMode.OBSERVE:
                        self._observe(ctx, "test", [f"exit {test.exit_code}"])
                    else:
                        self._stop(ctx, StopReason.TESTS_FAILED)
                        return
                if self._over_wall(ctx):
                    self._stop(ctx, StopReason.BUDGET_EXCEEDED, detail="wall-clock budget")
                    return

        if any(node.id == "challenge" for node in flow.nodes):
            challenge_node = flow.node("challenge")
            if challenge_node.mode is not GateMode.OFF:
                challenge = await self._challenge(ctx, proposal)
                ctx.challenge = challenge
                if not challenge.allow:
                    if challenge_node.mode is GateMode.OBSERVE:
                        self._observe(ctx, "challenge", [challenge.reason])
                    else:
                        self._stop(ctx, StopReason.CHALLENGE_FAILED, detail=challenge.reason)
                        return

        if not self._check_flakes(ctx):
            return
        verdict = await self._judge(ctx)
        ctx.verdict = verdict
        (ctx.run_dir / "verdict.json").write_text(
            verdict.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        if not verdict.allow:
            self._stop(ctx, StopReason.VERDICT_FAILED)
            return
        self._move(ctx, TaskState.PROVED)
        self._decide(ctx, "release")
        self._queue.append(
            ctx.task.id,
            "note",
            {"message": "release gate not crossed in v0; proof is ready"},
        )
        ctx.stop_reason = StopReason.COMPLETED

    def _repo(self, task: Task) -> GitRepo:
        repo = GitRepo(Path(task.repo).expanduser().resolve(), self._runner)
        if not repo.is_repo():
            raise ConfigError(f"not a git repository: {repo.path}")
        return repo

    def _apply_quarantine(self, flow: FlowSpec, path: Path, repo: GitRepo) -> FlowSpec:
        quarantine = load_quarantine(path, repo.path)
        spec = PathsSpec(allow=list(flow.paths.allow), deny=[*flow.paths.deny, *quarantine.paths])
        return flow.model_copy(update={"paths": spec})

    def _prepare_worktree(self, ctx: RunContext, repo: GitRepo, base: str) -> Path:
        repo.require_clean()
        destination = self._paths.worktrees / ctx.run_id / "repo"
        if destination.exists():
            repo.worktree_remove(destination)
        repo.worktree_add(destination, base)
        self._queue.append(ctx.task.id, "step.started", {"step": "worktree", "base": base})
        return destination

    def _recall_memory(self, ctx: RunContext) -> None:
        recall = getattr(self._memory, "recall", None)
        if not callable(recall):
            return
        try:
            statements = [str(item) for item in recall(limit=5)]
        except Exception as exc:
            self._queue.append(
                ctx.task.id,
                "memory.recall_failed",
                {"error": str(exc)[:500]},
            )
            return
        if not statements:
            return
        ctx.memory_recall = statements
        self._queue.append(
            ctx.task.id,
            "memory.recalled",
            {"view": "about_me", "statements": statements},
        )

    def _draft_plan(self, ctx: RunContext, repo: GitRepo, scenario_set: Path | None) -> None:
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
        ctx.plan = {
            "base_commit": repo.head(),
            "checks_sha": ctx.checks_sha,
            "checks_source": ctx.checks_source,
            "scenario_set": str(resolved),
            "scenario_ids": [s.id for s in scenarios.scenarios],
            "p0": scenarios.p0_ids,
            "p1": scenarios.p1_ids,
            "nodes": [node.id for node in ctx.flow.nodes],
        }

    def _load_plan_scenarios(self, ctx: RunContext, repo: GitRepo) -> None:
        if ctx.scenario_set is not None:
            return
        path = Path(ctx.plan["scenario_set"])
        scenarios = load_scenario_set(path)
        directory = ensure_outside(
            path.parent / scenarios.directory, repo.path, label="scenario set"
        )
        ctx.scenario_set = scenarios
        ctx.scenario_dir = directory

    def _latest_plan(self, task_id: str) -> dict[str, Any] | None:
        plan: dict[str, Any] | None = None
        for event in self._queue.events(task_id):
            if event.type == "plan.drafted":
                plan = dict(event.data)
        return plan

    async def _run_node(self, ctx: RunContext, step: str, node: Node) -> CommandResult:
        worktree = _required(ctx.worktree, "worktree")
        self._queue.append(ctx.task.id, "step.started", {"step": step})
        result = await asyncio.to_thread(
            self._verifier.run,
            node.argv(self.python),
            worktree,
            env={"PYTHONPATH": str(worktree)},
            timeout_s=node.timeout_s,
        )
        record = result.record(step)
        ctx.commands.append(record)
        self._queue.append(
            ctx.task.id, "step.finished", {"step": step, "exit_code": result.exit_code}
        )
        return result

    async def _propose(self, ctx: RunContext) -> Proposal | None:
        worktree = _required(ctx.worktree, "worktree")
        base_commit = _required(ctx.base_commit, "base commit")
        if self._harness is None:
            raise ConfigError(
                "no harness configured: pass --trace PATH (the live adapter lands in M1)"
            )
        self._queue.append(ctx.task.id, "attempt.started", {"attempt": ctx.task.attempts + 1})
        request = ProposalRequest(
            task_id=ctx.task.id,
            source_ref=ctx.task.source.ref,
            title=ctx.task.source.title,
            worktree=worktree,
            base_commit=base_commit,
        )
        try:
            proposal = await self._harness.propose(request)
        except HarnessError as exc:
            self._stop(ctx, StopReason.HARNESS_FAILED, detail=str(exc))
            return None
        (ctx.run_dir / "harness.json").write_text(
            proposal.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        if proposal.stop:
            ctx.proposal = proposal
            self._stop(ctx, StopReason.HARNESS_FAILED, detail=proposal.stop)
            return None
        self._queue.append(
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

    async def _challenge(self, ctx: RunContext, proposal: Proposal) -> Challenge:
        if self._harness is None:
            raise ConfigError("the flow asks for a challenge but no harness is configured")
        worktree = _required(ctx.worktree, "worktree")
        base_commit = _required(ctx.base_commit, "base commit")
        request = ProposalRequest(
            task_id=ctx.task.id,
            source_ref=ctx.task.source.ref,
            title=ctx.task.source.title,
            worktree=worktree,
            base_commit=base_commit,
        )
        challenge = await self._harness.challenge(request, proposal)
        (ctx.run_dir / "challenge.json").write_text(
            challenge.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        self._queue.append(
            ctx.task.id,
            "challenge.decided",
            challenge.model_dump(mode="json"),
        )
        return challenge

    async def _judge(self, ctx: RunContext) -> Verdict:
        scenario_set = _required(ctx.scenario_set, "scenario set")
        _required(ctx.scenario_dir, "scenario directory")
        _required(ctx.worktree, "worktree")
        tasks: list[tuple[Scenario, asyncio.Task[ScenarioOutcome]]] = []
        async with asyncio.TaskGroup() as group:
            for scenario in scenario_set.scenarios:
                tasks.append((scenario, group.create_task(self._run_scenario(ctx, scenario))))
        outcomes = [task.result() for _, task in tasks]
        return judge(outcomes, run_id=ctx.run_id)

    def _check_flakes(self, ctx: RunContext) -> bool:
        scenario_set = _required(ctx.scenario_set, "scenario set")
        ids = {scenario.id for scenario in scenario_set.scenarios}
        hits = [
            flake
            for flake in active_flakes(self._paths, task_id=ctx.task.id)
            if flake.scenario_id in ids
        ]
        if not hits:
            return True
        for flake in hits:
            self._queue.append(ctx.task.id, "flake", flake.model_dump(mode="json"))
        detail = ", ".join(f"{flake.scenario_id} ({flake.owner})" for flake in hits)
        self._stop(ctx, StopReason.FLAKY_TEST, detail=f"active flake: {detail}")
        return False

    async def _run_scenario(self, ctx: RunContext, scenario: Scenario) -> ScenarioOutcome:
        worktree = _required(ctx.worktree, "worktree")
        scenario_dir = _required(ctx.scenario_dir, "scenario directory")
        argv = scenario.argv(self.python, scenario_dir)
        result = await asyncio.to_thread(
            self._verifier.run,
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

    def _current_state(self, ctx: RunContext) -> TaskState:
        return self._queue.load(ctx.task.id).state

    def _observe(self, ctx: RunContext, gate: str, reasons: list[str]) -> None:
        detail = "; ".join(reasons) or "blocked"
        ctx.would_block.append(f"{gate}: {detail}")
        self._queue.append(
            ctx.task.id,
            "would_block",
            {"gate": gate, "reason": detail, "mode": GateMode.OBSERVE.value},
        )

    def _decide(self, ctx: RunContext, gate: str, *, already_approved: bool = False) -> GateVerdict:
        evidence: list[str] = []
        if ctx.reproduce is not None:
            evidence.append("the reproduction failed on the base commit")
        if ctx.verdict is not None:
            evidence.append(f"the verifier verdict is {'allow' if ctx.verdict.allow else 'block'}")
        if ctx.challenge is not None:
            evidence.append(
                f"the challenger verdict is {'allow' if ctx.challenge.allow else 'block'}"
            )
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
        verdict = self._decision.decide(context)
        ctx.decisions.append(verdict)
        payload = {"gate": gate, "mode": self._decision.mode, **verdict.model_dump(mode="json")}
        self._queue.append(ctx.task.id, "decision.made", payload)
        if isinstance(self._decision, ShadowGate):
            shadow = self._decision.last_shadow
            self._queue.append(
                ctx.task.id,
                "decision.shadow",
                {
                    "gate": gate,
                    "agree": None if shadow is None else verdict.action == shadow.action,
                    "shadow": None if shadow is None else shadow.model_dump(mode="json"),
                    "error": self._decision.last_error,
                },
            )
        return verdict

    def _require_approval(self, ctx: RunContext, gate: str) -> None:
        decisions = [
            event
            for event in self._queue.events(ctx.task.id)
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

    def _over_wall(self, ctx: RunContext) -> bool:
        elapsed_minutes = (self._clock() - ctx.started_at).total_seconds() / 60
        return elapsed_minutes > ctx.task.budget.wall_minutes

    def _move(self, ctx: RunContext, target: TaskState) -> None:
        self._queue.transition(ctx.task.id, target)
        ctx.state = target

    def _stop(self, ctx: RunContext, reason: StopReason, *, detail: str | None = None) -> None:
        ctx.stop_reason = reason
        if detail:
            ctx.error = detail
        current = self._current_state(ctx)
        if current is not TaskState.PLANNING and current not in TERMINAL:
            self._move(ctx, TaskState.BLOCKED)
        else:
            ctx.state = current
        LOG.info(
            "stop: %s",
            reason.value,
            extra={"run_id": ctx.run_id, "task_id": ctx.task.id},
        )

    def _abort(self, ctx: RunContext, detail: str, *, reason: StopReason | None = None) -> None:
        ctx.stop_reason = reason or StopReason.INTERNAL_ERROR
        ctx.error = detail
        current = self._current_state(ctx)
        if current not in TERMINAL:
            try:
                self._move(ctx, TaskState.BLOCKED)
            except WorksError:
                LOG.warning("could not mark the task blocked", exc_info=True)
        else:
            ctx.state = current

    @staticmethod
    def _reason_for(exc: WorksError) -> StopReason:
        from .errors import ConfigError, ConflictError

        if isinstance(exc, ConflictError):
            return StopReason.CONFLICT
        if isinstance(exc, ConfigError):
            return StopReason.CONFIG_ERROR
        return StopReason.INTERNAL_ERROR

    def _finish(self, ctx: RunContext, repo: GitRepo) -> RunRecord:
        finished = self._clock()
        duration_ms = int((finished - ctx.started_at).total_seconds() * 1000)
        state = self._current_state(ctx)
        files_changed: list[str] = []
        stats: list[DiffStatRow] = []
        diff = ""
        if ctx.worktree is not None and ctx.worktree.exists():
            worktree = GitRepo(ctx.worktree, self._runner)
            try:
                files_changed = worktree.changed_files(ctx.worktree)
                stats = [DiffStatRow.from_stat(stat) for stat in worktree.diff_stat(ctx.worktree)]
                diff = worktree.diff_text(ctx.worktree)
            except WorksError as exc:
                LOG.warning("could not collect the diff: %s", exc)
        proposal = ctx.proposal
        tokens = (proposal.tokens if proposal else 0) + (
            ctx.challenge.tokens if ctx.challenge else 0
        )
        usd = (proposal.usd if proposal else 0.0) + (ctx.challenge.usd if ctx.challenge else 0.0)
        findings: list[Finding] = []
        for event in self._queue.events(ctx.task.id):
            if event.type != "finding":
                continue
            try:
                findings.append(Finding.model_validate(event.data))
            except ValidationError as exc:
                LOG.warning("ignoring a malformed finding: %s", exc)
        draft = Evidence(
            run_id=ctx.run_id,
            task_id=ctx.task.id,
            flow=ctx.flow.flow,
            product=ctx.flow.product,
            source=f"{ctx.task.source.kind.value}:{ctx.task.source.ref}",
            task_kind=ctx.task.kind.value,
            base_commit=ctx.base_commit,
            checks_sha=ctx.checks_sha,
            state=state,
            stop_reason=ctx.stop_reason,
            model=proposal.model if proposal else None,
            provider=proposal.provider if proposal else None,
            prompt_name=proposal.prompt_name if proposal else None,
            prompt_sha256=proposal.prompt_sha256 if proposal else None,
            tokens=tokens,
            usd=usd,
            duration_ms=duration_ms,
            files_changed=files_changed,
            diff_stat=stats,
            policy=ctx.policy,
            risk=ctx.risk,
            decision=ctx.decisions[-1] if ctx.decisions else None,
            reproduce=ctx.reproduce,
            test=ctx.test,
            preview=ctx.preview,
            artifacts=ctx.artifacts,
            memory_recall=ctx.memory_recall,
            verdict=ctx.verdict,
            challenge=ctx.challenge,
            findings=findings,
            would_block=ctx.would_block,
            diff=diff,
        )
        from .features import feature_summary

        features = feature_summary(Path(ctx.task.repo), draft.model_dump(mode="json"))["features"]
        evidence = draft.model_copy(update={"features": features}).bind()
        _, md_path = write_evidence(ctx.run_dir, evidence)
        last_decision = ctx.decisions[-1] if ctx.decisions else None
        record = RunRecord(
            run_id=ctx.run_id,
            task_id=ctx.task.id,
            flow=ctx.flow.flow,
            state=state,
            stop_reason=ctx.stop_reason,
            base_commit=ctx.base_commit,
            checks_sha=ctx.checks_sha,
            task_kind=ctx.task.kind.value,
            risk_level=ctx.risk.level.value if ctx.risk is not None else None,
            risk_reasons=ctx.risk.reasons if ctx.risk is not None else [],
            decision_verb=last_decision.verb if last_decision is not None else None,
            decision_id=last_decision.decision_id if last_decision is not None else None,
            model=proposal.model if proposal else None,
            provider=proposal.provider if proposal else None,
            attempts=self._queue.load(ctx.task.id).attempts,
            tokens=tokens,
            usd=usd,
            started_at=ctx.started_at,
            finished_at=finished,
            duration_ms=duration_ms,
            evidence_md=str(md_path),
        )
        (ctx.run_dir / "run.json").write_text(
            record.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        if ctx.commands:
            with (ctx.run_dir / "commands.jsonl").open(
                "w", encoding="utf-8", newline="\n"
            ) as handle:
                for command in ctx.commands:
                    handle.write(command.model_dump_json() + "\n")
        verdict_label = None
        if ctx.verdict is not None:
            verdict_label = "allow" if ctx.verdict.allow else "block"
        self._ledger.append(
            LedgerRow(
                task_id=ctx.task.id,
                run_id=ctx.run_id,
                state=state,
                verdict=verdict_label,
                tokens=tokens,
                usd=usd,
            )
        )
        try:
            self._memory.record(
                task=self._queue.load(ctx.task.id),
                record=record,
                evidence=evidence,
            )
        except Exception as exc:
            LOG.warning("memory was not updated: %s", exc, extra={"run_id": ctx.run_id})
            self._queue.append(
                ctx.task.id,
                "memory.failed",
                {"run_id": ctx.run_id, "error": str(exc)[:500]},
            )
        else:
            if not isinstance(self._memory, NullMemory):
                self._queue.append(
                    ctx.task.id,
                    "memory.reported",
                    {"run_id": ctx.run_id, "app": "ppma", "via": "run"},
                )
        LOG.info(
            "run finished",
            extra={"run_id": ctx.run_id, "task_id": ctx.task.id, "duration_ms": duration_ms},
        )
        return record
