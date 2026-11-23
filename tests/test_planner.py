from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from works.approvals import approve_plan
from works.errors import ConfigError
from works.flow import load_flow
from works.harness.planner import HarnessPlanner, parse_plan_json
from works.planner import (
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
    collect_repository_context,
    deterministic_proposal,
    draft_plan,
    merge_proposal,
    plan_hash,
    validate_plan,
)
from works.queue import Queue
from works.records import Source, SourceKind, TaskState
from works.scenarios import load_scenario_set


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
