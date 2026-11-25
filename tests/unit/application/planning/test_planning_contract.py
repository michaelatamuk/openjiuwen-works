from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from works.adapters.queue.store import Queue
from works.application.execution.scenarios import Scenario, ScenarioSet
from works.application.planning.context import PlannerContext
from works.application.planning.deterministic import deterministic_proposal
from works.application.planning.impact import describe
from works.application.planning.linter import apply_critique, validate_plan
from works.application.planning.preflight import problems
from works.application.planning.store import PlanStore, make_plan_version
from works.domain.errors import ConfigError
from works.domain.flow import FlowSpec, Node, NodeKind
from works.domain.plan import PlanCritique, PlanMode, PlanProvenance, PlanStatus
from works.domain.records import Priority


def _repo(tmp_path: Path, *, with_test: bool = True) -> Path:
    repo = tmp_path / "repo"
    (repo / "calc").mkdir(parents=True)
    (repo / "calc" / "core.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    if with_test:
        (repo / "tests").mkdir()
        (repo / "tests" / "test_core.py").write_text(
            "from calc.core import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
            encoding="utf-8",
        )
    scenarios = repo / "scenarios"
    scenarios.mkdir()
    (scenarios / "add.py").write_text("raise SystemExit(1)\n", encoding="utf-8")
    return repo


def _context(repo: Path) -> PlannerContext:
    flow = FlowSpec(
        flow="fix-issue",
        product="Fixture",
        nodes=[
            Node(id="reproduce", kind=NodeKind.DETERMINISTIC, cmd="{python} -m pytest -q"),
            Node(id="build", kind=NodeKind.AGENTIC),
            Node(id="test", kind=NodeKind.DETERMINISTIC, cmd="{python} -m pytest -q"),
        ],
    )
    scenarios = ScenarioSet(
        directory="scenarios",
        scenarios=[
            Scenario(id="add-negative", priority=Priority.P0, script="add.py"),
            Scenario(id="add-positive", priority=Priority.P1, script="add.py"),
        ],
    )
    return PlannerContext(
        task_id="t-1",
        product="Fixture",
        task_kind="fix",
        source_ref="M13-1",
        source_title="calc/core.py subtracts",
        flow=flow,
        base_commit="0" * 40,
        checks_sha="1" * 64,
        checks_source="scenario set",
        scenario_set=repo / "scenarios.yaml",
        scenarios=scenarios,
        repo=repo,
        budget_tokens=400_000,
        budget_usd=10.0,
        source_text="the bug is in calc/core.py",
    )


def test_impact_names_the_test_that_covers_a_reported_path(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    lines, gaps = describe(repo, "the bug is in calc/core.py")

    assert gaps == []
    assert any("tests/test_core.py" in line for line in lines)


def test_impact_records_an_uncovered_path(tmp_path: Path) -> None:
    repo = _repo(tmp_path, with_test=False)

    lines, gaps = describe(repo, "the bug is in calc/core.py")

    assert lines == []
    assert gaps == ["calc/core.py"]


def test_the_deterministic_plan_includes_impact(tmp_path: Path) -> None:
    proposal = deterministic_proposal(_context(_repo(tmp_path)))

    assert any(line.startswith("Impact: calc/core.py") for line in proposal.verification)


def test_a_step_without_done_when_is_rejected(tmp_path: Path) -> None:
    context = _context(_repo(tmp_path))
    proposal = deterministic_proposal(context)
    proposal.steps[0].done_when = ""

    validation = validate_plan(proposal, context)

    assert validation.ok is False
    assert any("done_when" in error for error in validation.errors)


def test_preflight_rejects_a_missing_command_and_script(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    context = _context(repo)
    proposal = deterministic_proposal(context)
    proposal.steps[0].commands = ["definitely-not-a-real-binary --flag"]
    (repo / "scenarios" / "add.py").unlink()

    errors, _warnings = problems(proposal, context)

    assert any("not available" in error for error in errors)
    assert any("missing script" in error for error in errors)


def test_a_low_critic_score_blocks_the_plan(tmp_path: Path) -> None:
    context = _context(_repo(tmp_path))
    validation = validate_plan(deterministic_proposal(context), context)

    blocked = apply_critique(validation, PlanCritique(allow=True, score=0.2))

    assert blocked.ok is False
    assert any("critic scored" in error for error in blocked.errors)


def test_the_same_input_gives_the_same_plan_and_hash(tmp_path: Path) -> None:
    context = _context(_repo(tmp_path))
    first = deterministic_proposal(context)
    second = deterministic_proposal(context)
    assert first.model_dump() == second.model_dump()

    one = make_plan_version(
        context,
        first,
        version=1,
        mode=PlanMode.DETERMINISTIC,
        provenance=PlanProvenance(),
        validation=validate_plan(first, context),
    )
    two = make_plan_version(
        context,
        second,
        version=1,
        mode=PlanMode.DETERMINISTIC,
        provenance=PlanProvenance(),
        validation=validate_plan(second, context),
    )
    assert one.hash == two.hash


def test_a_person_edit_creates_a_new_version_and_supersedes(paths, tmp_path: Path) -> None:
    context = _context(_repo(tmp_path))
    proposal = deterministic_proposal(context)
    store = PlanStore(paths)
    first = make_plan_version(
        context,
        proposal,
        version=1,
        mode=PlanMode.DETERMINISTIC,
        provenance=PlanProvenance(),
        validation=validate_plan(proposal, context),
    )
    store.save(first)

    edited = [
        step.model_copy(update={"done_when": "a person tightened this"}) for step in first.steps
    ]
    revised = store.revise("t-1", edited, comment="tighter acceptance")

    assert revised.version == 2
    assert revised.status is PlanStatus.DRAFT
    assert "a person tightened this" in revised.steps[0].done_when
    assert revised.hash != first.hash
    assert store.load("t-1", 1).status is PlanStatus.SUPERSEDED
    assert "~" in store.diff("t-1")


def test_a_person_edit_cannot_invent_a_flow_node(paths, tmp_path: Path) -> None:
    context = _context(_repo(tmp_path))
    proposal = deterministic_proposal(context)
    store = PlanStore(paths)
    first = make_plan_version(
        context,
        proposal,
        version=1,
        mode=PlanMode.DETERMINISTIC,
        provenance=PlanProvenance(),
        validation=validate_plan(proposal, context),
    )
    store.save(first)
    bad = [first.steps[0].model_copy(update={"node": "publish"})]

    with pytest.raises(ConfigError, match="only rework the existing nodes"):
        store.revise("t-1", bad)


def test_the_plan_survives_a_queue_round_trip(paths, tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    queue = Queue(paths)
    from works.domain.records import Source, SourceKind

    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="M13-Q", title="calc/core.py subtracts"),
        flow="fix-issue",
        product="Fixture",
        repo=str(repo),
    )
    context = replace(_context(repo), task_id=task.id)
    proposal = deterministic_proposal(context)
    store = PlanStore(paths)
    store.save(
        make_plan_version(
            context,
            proposal,
            version=1,
            mode=PlanMode.DETERMINISTIC,
            provenance=PlanProvenance(),
            validation=validate_plan(proposal, context),
        )
    )

    assert store.load(task.id).task_id == task.id
