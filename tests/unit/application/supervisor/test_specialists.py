from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from works.adapters.harness.base import Proposal
from works.adapters.harness.fake import FakeHarness
from works.adapters.queue.store import Queue
from works.application.run_context import RunContext
from works.application.supervisor import verification
from works.domain.errors import ConfigError
from works.domain.evidence import Evidence, render_summary
from works.domain.evidence.render import render_markdown
from works.domain.flow import GateMode, load_flow_text
from works.domain.records import Challenge, Source, SourceKind
from works.domain.review import SpecialistReview

FLOW = """
flow: fix-issue
product: P
nodes:
  - id: reproduce
    kind: deterministic
    cmd: "true"
review:
  mode: "{mode}"
  specialists:
    security: ["calc/"]
    performance: ["calc/"]
"""


def _flow(mode: str = "observe"):
    return load_flow_text(FLOW.format(mode=mode))


def _trace(tmp_path: Path, specialists: dict[str, bool] | None = None) -> Path:
    path = tmp_path / "trace.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "specialists",
                "patch": "diff --git a/calc/core.py b/calc/core.py\n",
                "specialists": specialists or {},
            }
        ),
        encoding="utf-8",
    )
    return path


def _context(paths, repo, tmp_path: Path, flow):
    task, _ = Queue(paths).submit(
        source=Source(kind=SourceKind.TRACKER, ref="GH-1", title="change"),
        flow="fix-issue",
        product="P",
        repo=str(repo.path),
    )
    run_dir = paths.runs / "r-specialists"
    run_dir.mkdir(parents=True)
    return RunContext(
        task=task,
        flow=flow,
        run_id="r-specialists",
        run_dir=run_dir,
        worktree=tmp_path,
        base_commit="0" * 40,
        plan={},
    )


class Stub:
    def __init__(self, harness: FakeHarness, queue: Queue) -> None:
        self._harness = harness
        self._queue = queue


def test_specialists_are_selected_by_touched_paths() -> None:
    flow = _flow()

    selected = verification.specialists_for(flow, ["calc/core.py", "docs/x.md"])

    assert [area for area, _focus in selected] == ["security", "performance"]
    assert selected[0][1] == ["calc/core.py"]


def test_an_off_flow_selects_nothing() -> None:
    assert verification.specialists_for(_flow("off"), ["calc/core.py"]) == []


def test_observe_records_a_block_without_changing_the_challenge(
    paths, repo, tmp_path: Path
) -> None:
    ctx = _context(paths, repo, tmp_path, _flow("observe"))
    stub = Stub(FakeHarness(_trace(tmp_path, {"security": False})), Queue(paths))
    proposal = Proposal(patch="", touched_paths=["calc/core.py"])
    challenge = Challenge(allow=True, reason="primary allowed")

    result = asyncio.run(verification._specialists(stub, ctx, proposal, challenge))

    assert result.allow is True
    assert result.reason == "primary allowed"
    assert [item.area for item in ctx.specialists] == ["security", "performance"]
    assert ctx.specialists[0].allow is False
    assert (ctx.run_dir / "specialists.json").exists()
    events = [event.type for event in Queue(paths).events(ctx.task.id)]
    assert events.count("specialist.reviewed") == 2


def test_enforce_lets_a_specialist_block_the_change(paths, repo, tmp_path: Path) -> None:
    ctx = _context(paths, repo, tmp_path, _flow("enforce"))
    stub = Stub(FakeHarness(_trace(tmp_path, {"security": False})), Queue(paths))
    proposal = Proposal(patch="", touched_paths=["calc/core.py"])
    challenge = Challenge(allow=True, reason="primary allowed")

    result = asyncio.run(verification._specialists(stub, ctx, proposal, challenge))

    assert result.allow is False
    assert "specialist blocked" in result.reason
    assert "security" in result.reason


def test_a_harness_without_specialists_is_a_config_error(paths, repo, tmp_path: Path) -> None:
    ctx = _context(paths, repo, tmp_path, _flow("observe"))

    class NoReviews:
        supports_reviews = False

    stub = Stub(NoReviews(), Queue(paths))  # type: ignore[arg-type]
    proposal = Proposal(patch="", touched_paths=["calc/core.py"])

    with pytest.raises(ConfigError, match="does not support specialist reviews"):
        asyncio.run(
            verification._specialists(stub, ctx, proposal, Challenge(allow=True, reason="ok"))
        )


def test_evidence_records_and_renders_the_reviews() -> None:
    from tests.unit.domain.test_evidence import fixed_evidence

    review = SpecialistReview(
        area="security",
        allow=False,
        reason="the token is logged",
        concerns=["remove the token from the log line"],
        model="m",
        provider="p",
    )
    evidence = fixed_evidence().model_copy(update={"specialists": [review]})

    page = render_markdown(evidence)
    summary = render_summary(evidence)

    assert "## Specialist reviews" in page
    assert "security · BLOCK" in page
    assert "Specialist reviews: security block." in summary
    assert evidence.bind().proof_sha256 != fixed_evidence().bind().proof_sha256


def test_an_old_proof_keeps_its_hash_without_specialists() -> None:
    from tests.unit.domain.test_evidence import fixed_evidence

    evidence = fixed_evidence()
    original = evidence.bind().proof_sha256
    raw = json.loads(evidence.model_dump_json())
    raw.pop("specialists")
    old = Evidence.model_validate(raw)

    assert old.bind().proof_sha256 == original


def test_review_spec_rejects_unknown_areas() -> None:
    with pytest.raises(ConfigError, match="unknown specialist area"):
        load_flow_text(FLOW.format(mode="observe").replace("performance", "marketing"))


def test_review_mode_needs_a_specialist() -> None:
    with pytest.raises(ConfigError, match="needs at least one specialist"):
        load_flow_text(
            """
flow: fix-issue
product: P
nodes:
  - id: reproduce
    kind: deterministic
    cmd: "true"
review:
  mode: observe
"""
        )


def test_review_defaults_are_off() -> None:
    flow = load_flow_text(
        """
flow: fix-issue
product: P
nodes:
  - id: reproduce
    kind: deterministic
    cmd: "true"
"""
    )

    assert flow.review.mode is GateMode.OFF
    assert flow.review.specialists == {}
