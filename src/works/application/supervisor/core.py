"""The supervisor owns the loop. CLI commands only call it; they never act on their own."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from works.adapters.git.repo import GitRepo
from works.adapters.harness.base import Harness, Proposal
from works.adapters.processes.runner import CommandResult, CommandRunner
from works.adapters.queue.ledger import Ledger
from works.adapters.queue.store import Queue
from works.application.approvals.decisions import (
    DecisionPort,
    GateVerdict,
    build_decision_port,
)
from works.application.execution.quarantine import load as load_quarantine
from works.application.execution.scenarios import Scenario
from works.application.execution.verifier import LocalVerifier, Verifier
from works.application.memory.ppma import Memory, NullMemory
from works.application.planning.service import (
    Critic,
    PlanMode,
    Planner,
    PlannerContext,
    PlanStore,
)
from works.application.run_context import RunContext, new_run_id
from works.application.supervisor import execution, planning, recording, verification
from works.config.logging import get_logger
from works.config.paths import WorksPaths
from works.domain.errors import (
    ConfigError,
    ConflictError,
    PolicyError,
    StateError,
    WorksError,
)
from works.domain.flow import FlowSpec, Node, PathsSpec
from works.domain.records import (
    Challenge,
    RunRecord,
    ScenarioOutcome,
    StopReason,
    Task,
    TaskState,
    Verdict,
)
from works.domain.state import TERMINAL
from works.domain.trusted import load_trusted_flow

LOG = get_logger("supervisor")

__all__ = ["Supervisor"]


class Supervisor:
    """Owns one task run: plan, build, verify, prove and record."""

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
        planner_mode: str | None = None,
        planner: Planner | None = None,
        critic: Critic | None = None,
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
        try:
            self._planner_mode = PlanMode(planner_mode or PlanMode.DETERMINISTIC.value)
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
        self._planner = planner
        self._critic = critic
        self._plans = PlanStore(paths)

    @property
    def python(self) -> str:
        if self._python:
            return self._python
        import sys

        return sys.executable

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
        current_base = repo.head()
        base = str(plan["base_commit"]) if plan is not None else current_base
        trusted = load_trusted_flow(repo, base, task.flow, self._flows_dir)
        flow = trusted.flow
        if plan is not None:
            planned_sha = plan.get("checks_sha")
            stale = plan.get("base_commit") != current_base or (
                planned_sha and planned_sha != trusted.checks_sha
            )
            if stale:
                if task.state is not TaskState.PLANNING:
                    raise ConflictError(
                        "the plan is stale; draft a new plan and approve it before building"
                    )
                replan_scenarios = scenario_set or (
                    Path(plan["scenario_set"]) if plan.get("scenario_set") else None
                )
                await self.replan(task_id, scenario_set=replan_scenarios)
                plan = self._latest_plan(task_id)
                base = str(plan["base_commit"]) if plan else current_base
                trusted = load_trusted_flow(repo, base, task.flow, self._flows_dir)
                flow = trusted.flow
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

    def _repo(self, task: Task) -> GitRepo:
        repo = GitRepo(Path(task.repo).expanduser().resolve(), self._runner)
        if not repo.is_repo():
            raise ConfigError(f"not a git repository: {repo.path}")
        return repo

    def _apply_quarantine(self, flow: FlowSpec, path: Path, repo: GitRepo) -> FlowSpec:
        quarantine = load_quarantine(path, repo.path)
        spec = PathsSpec(allow=list(flow.paths.allow), deny=[*flow.paths.deny, *quarantine.paths])
        return flow.model_copy(update={"paths": spec})

    def _current_state(self, ctx: RunContext) -> TaskState:
        return self._queue.load(ctx.task.id).state

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
        from works.domain.errors import ConfigError, ConflictError

        if isinstance(exc, ConflictError):
            return StopReason.CONFLICT
        if isinstance(exc, ConfigError):
            return StopReason.CONFIG_ERROR
        if isinstance(exc, PolicyError):
            return StopReason.POLICY_VIOLATION
        return StopReason.INTERNAL_ERROR

    # planning
    def plan_run(self, task_id: str, *, scenario_set: Path | None = None) -> dict[str, Any]:
        return planning.plan_run(self, task_id, scenario_set=scenario_set)

    async def draft_task_plan(self, task_id: str, *, scenario_set: Path) -> Any:
        return await planning.draft_task_plan(self, task_id, scenario_set=scenario_set)

    async def replan(self, task_id: str, *, scenario_set: Path | None = None) -> Any:
        return await planning.replan(self, task_id, scenario_set=scenario_set)

    async def draft_alternative_plans(
        self,
        task_id: str,
        *,
        scenario_set: Path,
        planners: dict[str, Planner],
        mode: str,
    ) -> dict[str, Any]:
        return await planning.draft_alternative_plans(
            self, task_id, scenario_set=scenario_set, planners=planners, mode=mode
        )

    def _planner_context(
        self, ctx: RunContext, repo: GitRepo, scenario_set: Path | None
    ) -> PlannerContext:
        return planning._planner_context(self, ctx, repo, scenario_set)

    async def _draft_plan(self, ctx: RunContext, repo: GitRepo, scenario_set: Path | None) -> None:
        return await planning._draft_plan(self, ctx, repo, scenario_set)

    def _load_plan_scenarios(self, ctx: RunContext, repo: GitRepo) -> None:
        return planning._load_plan_scenarios(self, ctx, repo)

    def _latest_plan(self, task_id: str) -> dict[str, Any] | None:
        return planning._latest_plan(self, task_id)

    # execution
    async def _execute(
        self,
        ctx: RunContext,
        repo: GitRepo,
        approve_plan: bool,
        scenario_set: Path | None,
    ) -> None:
        return await execution._execute(self, ctx, repo, approve_plan, scenario_set)

    async def _prepare(self, ctx: RunContext, repo: GitRepo, scenario_set: Path | None) -> bool:
        return await execution._prepare(self, ctx, repo, scenario_set)

    def _approve_plan(self, ctx: RunContext, repo: GitRepo, approve_plan: bool) -> bool:
        return execution._approve_plan(self, ctx, repo, approve_plan)

    async def _build(self, ctx: RunContext, repo: GitRepo) -> list[str] | None:
        return await execution._build(self, ctx, repo)

    def _enforce_policy(
        self, ctx: RunContext, repo: GitRepo, proposal: Proposal, touched: list[str]
    ) -> bool:
        return execution._enforce_policy(self, ctx, repo, proposal, touched)

    async def _verify(self, ctx: RunContext, proposal: Proposal) -> bool:
        return await execution._verify(self, ctx, proposal)

    def _prove(self, ctx: RunContext) -> None:
        return execution._prove(self, ctx)

    def _prepare_worktree(self, ctx: RunContext, repo: GitRepo, base: str) -> Path:
        return execution._prepare_worktree(self, ctx, repo, base)

    def _recall_memory(self, ctx: RunContext) -> None:
        return execution._recall_memory(self, ctx)

    async def _run_node(self, ctx: RunContext, step: str, node: Node) -> CommandResult:
        return await execution._run_node(self, ctx, step, node)

    # verification
    async def _propose(self, ctx: RunContext) -> Proposal | None:
        return await verification._propose(self, ctx)

    async def _challenge(self, ctx: RunContext, proposal: Proposal) -> Challenge:
        return await verification._challenge(self, ctx, proposal)

    async def _judge(self, ctx: RunContext) -> Verdict:
        return await verification._judge(self, ctx)

    def _check_flakes(self, ctx: RunContext) -> bool:
        return verification._check_flakes(self, ctx)

    async def _run_scenario(self, ctx: RunContext, scenario: Scenario) -> ScenarioOutcome:
        return await verification._run_scenario(self, ctx, scenario)

    def _observe(self, ctx: RunContext, gate: str, reasons: list[str]) -> None:
        return verification._observe(self, ctx, gate, reasons)

    def _decide(self, ctx: RunContext, gate: str, *, already_approved: bool = False) -> GateVerdict:
        return verification._decide(self, ctx, gate, already_approved=already_approved)

    def _require_approval(self, ctx: RunContext, gate: str) -> None:
        return verification._require_approval(self, ctx, gate)

    def _over_wall(self, ctx: RunContext) -> bool:
        return verification._over_wall(self, ctx)

    # recording
    def _finish(self, ctx: RunContext, repo: GitRepo) -> RunRecord:
        return recording._finish(self, ctx, repo)
