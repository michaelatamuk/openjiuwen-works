from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from works.adapters.harness.openjiuwen.planner import HarnessPlanner, parse_plan_json
from works.adapters.processes.runner import SubprocessRunner
from works.adapters.queue.ledger import Ledger
from works.adapters.queue.store import Queue
from works.application.approvals.gates import approve_plan
from works.application.execution.scenarios import load_scenario_set
from works.application.planning.memory import PlanMemory
from works.application.planning.service import (
    DeterministicPlanner,
    PlanCritique,
    PlanMode,
    PlannerContext,
    PlannerOutput,
    PlanProposal,
    PlanProvenance,
    PlanStatus,
    PlanStep,
    PlanStore,
    PlanVersion,
    collect_repository_context,
    deterministic_proposal,
    draft_alternatives,
    draft_plan,
    merge_proposal,
    plan_deviations,
    plan_hash,
    validate_plan,
)
from works.application.supervisor import Supervisor
from works.domain.errors import ConfigError
from works.domain.flow import load_flow
from works.domain.records import Source, SourceKind, TaskState


def context(paths, repo, scenario_set: Path, *, task_id: str = "t-plan") -> PlannerContext:
    flow = load_flow(Path("flows/fix-issue.yaml"))
    scenarios = load_scenario_set(scenario_set)
    repository = collect_repository_context(repo.path)
    return PlannerContext(
        task_id=task_id,
        product="openjiuwen",
        task_kind="fix",
        source_ref="GH-1",
        source_title="add subtracts",
        flow=flow,
        base_commit=repo.head(),
        checks_sha="checks",
        checks_source="trusted",
        scenario_set=scenario_set,
        scenarios=scenarios,
        repo=repo.path,
        budget_tokens=400_000,
        budget_usd=10.0,
        file_tree=repository.file_tree,
        manifests=repository.manifests,
        readme=repository.readme,
    )


class FakePlanner:
    name = "fake"

    def __init__(self, proposal: PlanProposal) -> None:
        self.proposal = proposal

    async def draft(self, ctx: PlannerContext) -> PlannerOutput:
        return PlannerOutput(
            proposal=self.proposal,
            provenance=PlanProvenance(
                planner=self.name, provider="fake", model="fake-model", tokens=12, usd=0.001
            ),
        )


class FakeRepairPlanner:
    name = "fake-repair"

    def __init__(self) -> None:
        self.calls = 0

    async def draft(self, ctx: PlannerContext) -> PlannerOutput:
        return PlannerOutput(
            proposal=PlanProposal(
                summary="Bad plan",
                steps=[PlanStep(id="s1", node="build", title="Bad", files=["tests/test_core.py"])],
            ),
            provenance=PlanProvenance(planner=self.name, provider="fake", model="fake"),
        )

    async def draft_with_feedback(
        self, ctx: PlannerContext, previous: PlanProposal, errors: list[str]
    ) -> PlannerOutput:
        self.calls += 1
        return PlannerOutput(
            proposal=PlanProposal(
                summary="Repaired plan",
                steps=[PlanStep(id="s1", node="build", title="Good", files=["calc/core.py"])],
            ),
            provenance=PlanProvenance(planner=self.name, provider="fake", model="fake"),
        )


class FakeCritic:
    name = "fake-critic"

    def __init__(self, allow: bool) -> None:
        self.allow = allow

    async def review(self, ctx: PlannerContext, plan) -> PlanCritique:
        return PlanCritique(
            allow=self.allow,
            score=0.5,
            concerns=[] if self.allow else ["the plan is too broad"],
        )


def test_parse_plan_json_accepts_fences_and_rejects_prose() -> None:
    proposal = parse_plan_json('Here is the plan:\n```json\n{"summary": "ok", "steps": []}\n```\n')
    assert proposal.summary == "ok"
    with pytest.raises(ConfigError, match="no JSON"):
        parse_plan_json("no plan here")


def test_the_harness_planner_rejects_providers_without_a_read_only_mode(tmp_path) -> None:
    with pytest.raises(ConfigError, match="does not support"):
        HarnessPlanner(
            provider="dsh",
            model="x",
            base_url="https://example.invalid",
            api_key="x",
            prompt_path=tmp_path / "plan.md",
        )


def test_repository_context_is_bounded_and_hides_git(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "core.py").write_text("x", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x", encoding="utf-8")

    context = collect_repository_context(tmp_path)

    assert "src/core.py" in context.file_tree
    assert not any(part.startswith(".git") for part in context.file_tree)


def test_deterministic_plan_covers_the_flow_and_leaves(paths, repo, scenario_set) -> None:
    ctx = context(paths, repo, scenario_set)

    proposal = deterministic_proposal(ctx)
    validation = validate_plan(proposal, ctx)

    assert validation.ok, validation.errors
    assert [step.node for step in proposal.steps] == [node.id for node in ctx.flow.nodes]
    assert "add-positive" in " ".join(proposal.verification)


def test_the_linter_rejects_unknown_nodes_test_edits_and_dangerous_commands(
    paths, repo, scenario_set
) -> None:
    ctx = context(paths, repo, scenario_set)
    proposal = deterministic_proposal(ctx).model_copy(
        update={
            "steps": [
                *deterministic_proposal(ctx).steps,
                PlanStep(
                    id="bad",
                    node="deploy",
                    title="Deploy",
                    files=["tests/test_core.py"],
                    commands=["git push origin main"],
                    done_when="it is live",
                ),
            ]
        }
    )

    validation = validate_plan(proposal, ctx)

    assert not validation.ok
    assert any("unknown flow node" in item for item in validation.errors)
    assert any("test path" in item for item in validation.errors)
    assert any("side-effecting command" in item for item in validation.errors)


def test_read_only_inspection_may_name_test_files(paths, repo, scenario_set) -> None:
    ctx = context(paths, repo, scenario_set)
    proposal = deterministic_proposal(ctx).model_copy(
        update={
            "steps": [
                *deterministic_proposal(ctx).steps,
                PlanStep(
                    id="inspect",
                    node="build",
                    title="Inspect the failing test",
                    reads=["tests/test_core.py"],
                    done_when="the failing assertion is understood",
                ),
            ]
        }
    )

    validation = validate_plan(proposal, ctx)

    assert validation.ok, validation.errors


def test_merge_keeps_required_nodes_and_adds_model_detail(paths, repo, scenario_set) -> None:
    ctx = context(paths, repo, scenario_set)
    base = deterministic_proposal(ctx)
    model = PlanProposal(
        summary="Fix add",
        steps=[PlanStep(id="s1", node="build", title="Change add", files=["calc/core.py"])],
    )

    merged = merge_proposal(base, model, ctx)

    nodes = [step.node for step in merged.steps]
    assert nodes.count("build") == 1
    assert "reproduce" in nodes and "test" in nodes and "challenge" in nodes
    assert "calc/core.py" in " ".join(file for step in merged.steps for file in step.files)


def test_approved_plan_memory_recalls_similar_plans(paths, repo, scenario_set) -> None:
    ctx = context(paths, repo, scenario_set)
    store = PlanStore(paths)
    plan = asyncio.run(draft_plan(ctx, store=store, mode=PlanMode.DETERMINISTIC))
    approved = plan.model_copy(update={"status": PlanStatus.APPROVED, "approved_by": "cli"})

    memory = PlanMemory(paths)
    memory.remember(approved, by="cli")
    memory.remember(approved, by="cli")

    recalled = memory.recall(product="openjiuwen", flow="fix-issue")
    assert len(recalled) == 1
    assert recalled[0]["plan_id"] == plan.plan_id
    assert recalled[0]["steps"]


def test_plan_drift_is_the_difference_between_named_and_touched_files() -> None:
    plan = PlanVersion(
        plan_id="p-1",
        task_id="t-1",
        version=1,
        flow="fix-issue",
        product="openjiuwen",
        base_commit="a",
        checks_sha="b",
        checks_source="c",
        scenario_set="d",
        steps=[PlanStep(id="s1", node="build", files=["calc/core.py"])],
    )

    assert plan_deviations(plan, ["calc/core.py"]) == []
    assert plan_deviations(plan, ["calc/core.py", "tests/test_core.py"]) == ["tests/test_core.py"]
    assert plan_deviations(plan.model_copy(update={"steps": []}), ["anything.py"]) == []


def test_plan_store_versions_and_hashes(paths, repo, scenario_set) -> None:
    ctx = context(paths, repo, scenario_set)
    store = PlanStore(paths)

    first = asyncio.run(
        draft_plan(ctx, store=store, mode=PlanMode.DETERMINISTIC, planner=DeterministicPlanner())
    )
    second = asyncio.run(
        draft_plan(ctx, store=store, mode=PlanMode.DETERMINISTIC, planner=DeterministicPlanner())
    )

    assert first.version == 1 and second.version == 2
    assert store.load(ctx.task_id).version == 2
    assert store.versions(ctx.task_id) == [1, 2]
    assert plan_hash(first) == first.hash
    assert first.status is PlanStatus.VALIDATED


def test_assisted_plan_uses_the_model_proposal(paths, repo, scenario_set) -> None:
    ctx = context(paths, repo, scenario_set)
    store = PlanStore(paths)
    planner = FakePlanner(
        PlanProposal(
            summary="Model plan",
            open_questions=["Is the public API stable?"],
            steps=[
                PlanStep(
                    id="s1",
                    node="build",
                    title="Implement add",
                    intent="Return the sum",
                    files=["calc/core.py"],
                    done_when="tests pass",
                )
            ],
        )
    )

    plan = asyncio.run(draft_plan(ctx, store=store, mode=PlanMode.ASSISTED, planner=planner))

    assert plan.provenance.provider == "fake"
    assert plan.provenance.tokens == 12
    assert plan.summary == "Model plan"
    assert plan.open_questions == ["Is the public API stable?"]
    assert plan.status is PlanStatus.VALIDATED
    assert any(step.node == "reproduce" for step in plan.steps)


def test_deep_mode_blocks_on_a_critic_rejection(paths, repo, scenario_set) -> None:
    ctx = context(paths, repo, scenario_set)
    store = PlanStore(paths)
    planner = FakePlanner(deterministic_proposal(ctx))

    plan = asyncio.run(
        draft_plan(
            ctx,
            store=store,
            mode=PlanMode.DEEP,
            planner=planner,
            critic=FakeCritic(allow=False),
        )
    )

    assert plan.validation is not None and not plan.validation.ok
    assert any("critic rejected" in item for item in plan.validation.errors)


def test_lint_failure_is_repaired_once_before_storage(paths, repo, scenario_set) -> None:
    ctx = context(paths, repo, scenario_set)
    store = PlanStore(paths)
    planner = FakeRepairPlanner()

    plan = asyncio.run(draft_plan(ctx, store=store, mode=PlanMode.ASSISTED, planner=planner))

    assert planner.calls == 1
    assert plan.status is PlanStatus.VALIDATED
    assert plan.summary == "Repaired plan"
    assert any("Repaired after" in note for note in plan.notes)


def test_alternatives_are_labelled_and_stored_without_touching_the_plan(
    paths, repo, scenario_set
) -> None:
    ctx = context(paths, repo, scenario_set)
    store = PlanStore(paths)
    planners = {
        "minimal": FakePlanner(
            PlanProposal(
                summary="Minimal",
                steps=[PlanStep(id="s1", node="build", title="Minimal", files=["calc/core.py"])],
            )
        ),
        "spec": FakePlanner(
            PlanProposal(
                summary="Spec",
                steps=[PlanStep(id="s1", node="build", title="Spec", files=["calc/core.py"])],
            )
        ),
    }

    result = asyncio.run(
        draft_alternatives(ctx, store=store, mode=PlanMode.ASSISTED, planners=planners)
    )

    assert set(result) == {"minimal", "spec"}
    assert result["minimal"].status is PlanStatus.ALTERNATIVE
    assert store.alternatives(ctx.task_id)
    assert store.versions(ctx.task_id) == []


def test_spec_mode_writes_requirements_design_and_tasks(paths, repo, scenario_set) -> None:
    ctx = context(paths, repo, scenario_set)
    store = PlanStore(paths)
    planner = FakePlanner(
        PlanProposal(
            summary="Spec plan",
            requirements_md="# Requirements\n\nadd must sum.",
            design_md="# Design\n\nChange one operator.",
            tasks_md="# Tasks\n\n- change add",
            steps=[PlanStep(id="s1", node="build", title="Change add", files=["calc/core.py"])],
        )
    )

    plan = asyncio.run(draft_plan(ctx, store=store, mode=PlanMode.SPEC, planner=planner))

    assert plan.status is PlanStatus.VALIDATED
    directory = store.directory(ctx.task_id)
    assert (directory / "v1.requirements.md").is_file()
    assert (directory / "v1.design.md").is_file()
    assert (directory / "v1.tasks.md").is_file()
    assert plan.requirements_md.startswith("# Requirements")


def test_spec_mode_blocks_without_the_three_documents(paths, repo, scenario_set) -> None:
    ctx = context(paths, repo, scenario_set)
    store = PlanStore(paths)
    planner = FakePlanner(
        PlanProposal(
            summary="Incomplete spec",
            steps=[PlanStep(id="s1", node="build", title="Change add", files=["calc/core.py"])],
        )
    )

    plan = asyncio.run(draft_plan(ctx, store=store, mode=PlanMode.SPEC, planner=planner))

    assert plan.status is PlanStatus.DRAFT
    assert plan.validation is not None and not plan.validation.ok
    assert any("spec mode needs" in item for item in plan.validation.errors)


def test_auto_mode_chooses_deep_for_a_high_risk_plan(paths, repo, scenario_set) -> None:
    ctx = context(paths, repo, scenario_set)
    store = PlanStore(paths)
    planner = FakePlanner(
        PlanProposal(
            summary="Change auth",
            steps=(
                [PlanStep(id="s1", node="build", title="Change auth", files=["auth/session.py"])]
            ),
        )
    )

    plan = asyncio.run(
        draft_plan(
            ctx,
            store=store,
            mode=PlanMode.AUTO,
            planner=planner,
            critic=FakeCritic(allow=True),
        )
    )

    assert plan.provenance.mode == "auto"
    assert plan.critique is not None
    assert any("Auto selected deep" in note for note in plan.notes)


def test_auto_mode_chooses_assisted_for_a_low_risk_plan(paths, repo, scenario_set) -> None:
    ctx = context(paths, repo, scenario_set)
    store = PlanStore(paths)
    planner = FakePlanner(
        PlanProposal(
            summary="Change add",
            steps=[PlanStep(id="s1", node="build", title="Change add", files=["calc/core.py"])],
        )
    )

    plan = asyncio.run(
        draft_plan(
            ctx,
            store=store,
            mode=PlanMode.AUTO,
            planner=planner,
            critic=FakeCritic(allow=False),
        )
    )

    assert plan.provenance.mode == "auto"
    assert plan.critique is None
    assert any("Auto selected assisted" in note for note in plan.notes)


def test_shadow_mode_never_changes_the_executed_plan(paths, repo, scenario_set) -> None:
    ctx = context(paths, repo, scenario_set)
    store = PlanStore(paths)
    planner = FakePlanner(
        PlanProposal(
            summary="Shadow proposal",
            steps=[PlanStep(id="s1", node="build", title="Different build")],
        )
    )

    plan = asyncio.run(draft_plan(ctx, store=store, mode=PlanMode.SHADOW, planner=planner))

    assert plan.summary.startswith("Deterministic plan")
    shadow = store.shadow(ctx.task_id)
    assert shadow is not None
    assert shadow.status is PlanStatus.SHADOW
    assert shadow.summary == "Shadow proposal"


def test_replan_keeps_the_task_in_planning_and_supersedes_the_previous_version(
    paths, repo, scenario_set
) -> None:
    queue = Queue(paths)
    queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="GH-REPLAN", title="add subtracts"),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(repo.path),
    )
    task = queue.list_tasks()[-1]
    queue.transition(task.id, TaskState.REPRODUCING)
    queue.transition(task.id, TaskState.REPRODUCED)
    queue.transition(task.id, TaskState.PLANNING)
    supervisor = Supervisor(
        paths=paths,
        queue=queue,
        ledger=Ledger(paths.ledger),
        harness=None,
        runner=SubprocessRunner(),
        planner_mode="deterministic",
    )

    first = asyncio.run(supervisor.replan(task.id, scenario_set=scenario_set))
    second = asyncio.run(supervisor.replan(task.id))

    assert first.version == 1 and second.version == 2
    assert queue.load(task.id).state is TaskState.PLANNING
    assert PlanStore(paths).load(task.id, 1).status is PlanStatus.SUPERSEDED
    assert len([e for e in queue.events(task.id) if e.type == "plan.drafted"]) == 2


def test_plan_eval_summarizes_stored_plans(paths, repo, scenario_set) -> None:
    from works.application.planning.eval import evaluate

    queue = Queue(paths)
    queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="GH-EVAL", title="add subtracts"),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(repo.path),
    )
    task = queue.list_tasks()[-1]
    ctx = context(paths, repo, scenario_set, task_id=task.id)
    store = PlanStore(paths)
    plan = asyncio.run(draft_plan(ctx, store=store, mode=PlanMode.DETERMINISTIC))

    payload = evaluate(paths)

    assert payload["tasks"] == 1
    assert payload["plans"] == 1
    assert payload["validated"] == 1
    assert payload["by_mode"]["deterministic"]["plans"] == 1
    assert payload["rows"][0]["plan_id"] == plan.plan_id


def test_approval_is_bound_to_the_plan_hash(paths, repo, scenario_set) -> None:
    queue = Queue(paths)
    queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="GH-1", title="add subtracts"),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(repo.path),
    )
    task = queue.list_tasks()[-1]
    ctx = context(paths, repo, scenario_set, task_id=task.id)
    store = PlanStore(paths)
    plan = asyncio.run(draft_plan(ctx, store=store, mode=PlanMode.DETERMINISTIC))
    queue.transition(task.id, TaskState.REPRODUCING)
    queue.transition(task.id, TaskState.REPRODUCED)
    queue.transition(task.id, TaskState.PLANNING)
    queue.append(
        task.id,
        "plan.drafted",
        {
            "plan_id": plan.plan_id,
            "version": plan.version,
            "hash": plan.hash,
            "base_commit": plan.base_commit,
            "checks_sha": plan.checks_sha,
            "scenario_set": plan.scenario_set,
        },
    )

    with pytest.raises(ConfigError, match="plan hash"):
        approve_plan(paths, task.id, plan_hash="wrong")

    updated, event = approve_plan(paths, task.id, plan_hash=plan.hash)

    assert updated.state is TaskState.PLAN_APPROVED
    assert event.data["plan_hash"] == plan.hash
    approved = store.load(task.id)
    assert approved.status is PlanStatus.APPROVED
    assert approved.approved_by == "cli"
