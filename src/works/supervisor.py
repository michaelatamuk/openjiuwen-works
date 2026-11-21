"""The supervisor owns the loop. CLI commands only call it; they never act on their own."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import WorksPaths
from .errors import ConfigError, HarnessError, StateError, WorksError
from .evidence import DiffStatRow, Evidence, write_evidence
from .flow import FlowSpec, Node, PathsSpec, find_flow, load_flow
from .gitops import GitRepo
from .harness.base import Harness, Proposal, ProposalRequest
from .ledger import Ledger
from .logs import get_logger
from .memory import Memory, NullMemory
from .policy import PolicyReport, check_patch, check_paths, paths_from_patch
from .quarantine import ensure_outside
from .quarantine import load as load_quarantine
from .queue import Queue
from .records import (
    CommandRecord,
    LedgerRow,
    RunRecord,
    ScenarioOutcome,
    StopReason,
    Task,
    TaskState,
    Verdict,
)
from .runner import CommandResult, CommandRunner
from .scenarios import Scenario, ScenarioSet, judge, load_scenario_set
from .state import TERMINAL

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
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    commands: list[CommandRecord] = field(default_factory=list)
    reproduce: CommandRecord | None = None
    test: CommandRecord | None = None
    proposal: Proposal | None = None
    verdict: Verdict | None = None
    policy: PolicyReport = field(default_factory=lambda: PolicyReport(ok=True))
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

    @property
    def python(self) -> str:
        if self._python:
            return self._python
        import sys

        return sys.executable

    def plan_run(self, task_id: str, *, scenario_set: Path | None = None) -> dict[str, Any]:
        task = self._queue.load(task_id)
        flow = self._load_flow(task)
        repo = self._repo(task)
        payload: dict[str, Any] = {
            "task_id": task.id,
            "flow": flow.flow,
            "product": flow.product,
            "repo": str(repo),
            "state": task.state.value,
            "nodes": [
                {"id": node.id, "kind": node.kind.value, "required": node.required}
                for node in flow.nodes
            ],
            "base_commit": repo.head() if repo.is_repo() else None,
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
        flow = self._load_flow(task)
        repo = self._repo(task)
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
            state=task.state,
            started_at=self._clock(),
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
            ctx.base_commit = repo.head()
            ctx.worktree = self._prepare_worktree(ctx, repo, ctx.base_commit)
            reproduce = await self._run_node(ctx, "reproduce", flow.node("reproduce"))
            ctx.reproduce = reproduce.record("reproduce")
            if reproduce.ok:
                ctx.state = TaskState.REPRODUCING
                self._stop(ctx, StopReason.NOT_REPRODUCIBLE)
                return
            self._move(ctx, TaskState.REPRODUCED)
            self._draft_plan(ctx, repo, scenario_set)
            self._move(ctx, TaskState.PLANNING)
            self._queue.append(task.id, "plan.drafted", ctx.plan)
        else:
            plan = self._latest_plan(ctx)
            if plan is None:
                raise StateError(f"cannot resume {task.state.value} without a plan")
            ctx.plan = plan
            ctx.base_commit = plan["base_commit"]
            stored = Path(plan["scenario_set"])
            scenario_set = scenario_set or stored
            ctx.worktree = self._prepare_worktree(ctx, repo, ctx.base_commit)

        gate = flow.gate("plan")
        current = self._current_state(ctx)
        already_approved = current is TaskState.PLAN_APPROVED
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

        violations = (
            check_paths(proposal.touched_paths, flow.paths)
            if proposal.applied
            else check_patch(proposal.patch, flow.paths)
        )
        if proposal.applied:
            worktree = _required(ctx.worktree, "worktree")
            touched = proposal.touched_paths or repo.all_changed_files(worktree)
            violations = check_paths(touched, flow.paths)
        ctx.policy = PolicyReport(ok=not violations, violations=violations)
        if violations:
            self._stop(ctx, StopReason.POLICY_VIOLATION)
            return

        if not proposal.applied:
            worktree = _required(ctx.worktree, "worktree")
            repo.apply_patch(worktree, proposal.patch, ctx.run_dir / "proposal.diff")
        self._move(ctx, TaskState.CHECKING)

        if any(node.id == "test" for node in flow.nodes):
            test = await self._run_node(ctx, "test", flow.node("test"))
            ctx.test = test.record("test")
            if not test.ok:
                self._stop(ctx, StopReason.TESTS_FAILED)
                return
            if self._over_wall(ctx):
                self._stop(ctx, StopReason.BUDGET_EXCEEDED, detail="wall-clock budget")
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
        self._queue.append(
            ctx.task.id,
            "note",
            {"message": "release gate not crossed in v0; proof is ready"},
        )
        ctx.stop_reason = StopReason.COMPLETED

    def _load_flow(self, task: Task) -> FlowSpec:
        return load_flow(find_flow(self._flows_dir, task.flow))

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

    def _latest_plan(self, ctx: RunContext) -> dict[str, Any] | None:
        plan: dict[str, Any] | None = None
        for event in self._queue.events(ctx.task.id):
            if event.type == "plan.drafted":
                plan = dict(event.data)
        return plan

    async def _run_node(self, ctx: RunContext, step: str, node: Node) -> CommandResult:
        worktree = _required(ctx.worktree, "worktree")
        self._queue.append(ctx.task.id, "step.started", {"step": step})
        result = await asyncio.to_thread(
            self._runner.run,
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

    async def _run_scenario(self, ctx: RunContext, scenario: Scenario) -> ScenarioOutcome:
        worktree = _required(ctx.worktree, "worktree")
        scenario_dir = _required(ctx.scenario_dir, "scenario directory")
        argv = scenario.argv(self.python, scenario_dir)
        result = await asyncio.to_thread(
            self._runner.run,
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
        tokens = proposal.tokens if proposal else 0
        evidence = Evidence(
            run_id=ctx.run_id,
            task_id=ctx.task.id,
            flow=ctx.flow.flow,
            product=ctx.flow.product,
            source=f"{ctx.task.source.kind.value}:{ctx.task.source.ref}",
            base_commit=ctx.base_commit,
            state=state,
            stop_reason=ctx.stop_reason,
            model=proposal.model if proposal else None,
            provider=proposal.provider if proposal else None,
            tokens=tokens,
            usd=proposal.usd if proposal else 0.0,
            duration_ms=duration_ms,
            files_changed=files_changed,
            diff_stat=stats,
            policy=ctx.policy,
            reproduce=ctx.reproduce,
            test=ctx.test,
            verdict=ctx.verdict,
            diff=diff,
        ).bind()
        _, md_path = write_evidence(ctx.run_dir, evidence)
        record = RunRecord(
            run_id=ctx.run_id,
            task_id=ctx.task.id,
            flow=ctx.flow.flow,
            state=state,
            stop_reason=ctx.stop_reason,
            base_commit=ctx.base_commit,
            model=proposal.model if proposal else None,
            provider=proposal.provider if proposal else None,
            attempts=self._queue.load(ctx.task.id).attempts,
            tokens=tokens,
            usd=proposal.usd if proposal else 0.0,
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
                usd=proposal.usd if proposal else 0.0,
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
        LOG.info(
            "run finished",
            extra={"run_id": ctx.run_id, "task_id": ctx.task.id, "duration_ms": duration_ms},
        )
        return record
