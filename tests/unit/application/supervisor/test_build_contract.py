from __future__ import annotations

import json
from datetime import UTC, datetime

from tests.unit.domain.test_evidence import fixed_evidence

from works.adapters.harness.base import Proposal
from works.application.run_context import RunContext
from works.application.supervisor.execution import _write_transcript
from works.domain.evidence import render_markdown
from works.domain.flow import FlowSpec, Node, NodeKind
from works.domain.plan import PlanStep, PlanVersion, plan_deviations
from works.domain.records import Source, SourceKind, StopReason, Task


def _context(tmp_path) -> RunContext:
    task = Task(
        id="t-build",
        flow="fix-issue",
        product="Fixture",
        repo=str(tmp_path),
        source=Source(kind=SourceKind.MANUAL, ref="B-1", title="build"),
    )
    flow = FlowSpec(
        flow="fix-issue",
        product="Fixture",
        nodes=[Node(id="build", kind=NodeKind.AGENTIC)],
    )
    return RunContext(
        task=task,
        flow=flow,
        run_id="r-1",
        run_dir=tmp_path,
        worktree=tmp_path,
        base_commit="0" * 40,
    )


def test_the_transcript_keeps_engine_provenance(tmp_path) -> None:
    ctx = _context(tmp_path)
    proposal = Proposal(
        patch="x",
        model="deepseek-chat",
        provider="deepseek",
        version="1.2.3",
        harness="native",
        prompt_name="build",
        prompt_sha256="a" * 64,
        tokens=100,
        usd=0.01,
        trace=["read calc.py"],
        notes=["changed one operator"],
    )

    _write_transcript(ctx, proposal)

    payload = json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))
    assert payload["version"] == "1.2.3"
    assert payload["trace"] == ["read calc.py"]
    assert ctx.artifacts and ctx.artifacts[0].kind == "transcript"
    assert ctx.artifacts[0].sha256


def test_a_file_outside_the_plan_is_a_deviation() -> None:
    plan = PlanVersion(
        plan_id="p-1",
        task_id="t-1",
        version=1,
        flow="fix-issue",
        product="Fixture",
        base_commit="0" * 40,
        checks_sha="1" * 64,
        checks_source="scenario set",
        scenario_set="scenarios.yaml",
        steps=[
            PlanStep(id="s1", node="build", title="edit", files=["calc/core.py"]),
        ],
        created_at=datetime.now(tz=UTC),
    )

    assert plan_deviations(plan, ["calc/core.py"]) == []
    assert plan_deviations(plan, ["calc/core.py", "calc/other.py"]) == ["calc/other.py"]


def test_the_page_names_the_next_step_on_a_blocked_run() -> None:
    evidence = fixed_evidence().model_copy(update={"stop_reason": StopReason.NOT_REPRODUCIBLE})
    page = render_markdown(evidence)

    assert "**Next step**" in page
    assert "add a failing test" in page


def test_the_transcript_redacts_credentials(tmp_path) -> None:
    ctx = _context(tmp_path)
    proposal = Proposal(
        patch="x",
        model="m",
        provider="p",
        version="1",
        harness="native",
        tokens=1,
        usd=0.0,
        trace=["export TOKEN=ghp_abcdefghijklmnopqrstuvwxyz"],
        notes=["used sk-abcdefghijklmnop"],
    )

    _write_transcript(ctx, proposal)

    text = (tmp_path / "transcript.json").read_text(encoding="utf-8")
    assert "ghp_" not in text and "sk-" not in text
    assert "[redacted]" in text
