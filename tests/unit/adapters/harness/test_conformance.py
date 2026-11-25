from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from works.adapters.harness.base import Proposal, ProposalRequest
from works.adapters.harness.fake import FakeHarness
from works.adapters.harness.version import package_version


def _trace(tmp_path: Path, **overrides) -> Path:
    payload = {
        "schema_version": 1,
        "name": "conformance",
        "model": "fake-builder-1",
        "provider": "fixture",
        "version": "fixture-9",
        "tokens": 10,
        "usd": 0.001,
        "patch": "diff --git a/calc.py b/calc.py\n",
    }
    payload.update(overrides)
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _request(tmp_path: Path) -> ProposalRequest:
    return ProposalRequest(
        task_id="t-1",
        source_ref="C-1",
        title="conformance",
        worktree=tmp_path,
        base_commit="0" * 40,
    )


def test_the_fake_harness_honours_the_proposal_contract(tmp_path: Path) -> None:
    proposal = asyncio.run(FakeHarness(_trace(tmp_path)).propose(_request(tmp_path)))

    assert isinstance(proposal, Proposal)
    assert proposal.provider and proposal.model and proposal.version
    assert proposal.harness == "fake"
    assert proposal.tokens >= 0 and proposal.usd >= 0
    assert proposal.patch.strip()


def test_the_fake_harness_honours_the_challenge_contract(tmp_path: Path) -> None:
    harness = FakeHarness(_trace(tmp_path))
    proposal = asyncio.run(harness.propose(_request(tmp_path)))

    challenge = asyncio.run(harness.challenge(_request(tmp_path), proposal))

    assert isinstance(challenge.allow, bool)
    assert challenge.model and challenge.provider and challenge.version
    assert challenge.tokens >= 0 and challenge.usd >= 0


def test_an_unknown_package_version_is_unknown() -> None:
    assert package_version("definitely-not-a-real-package") == "unknown"
    assert isinstance(package_version("openjiuwen"), str)


def test_a_trace_that_abstains_needs_no_patch(tmp_path: Path) -> None:
    proposal = asyncio.run(
        FakeHarness(_trace(tmp_path, patch="", stop="no safe change")).propose(_request(tmp_path))
    )
    assert proposal.stop == "no safe change"
    assert proposal.patch == ""


def test_a_trace_without_a_patch_or_stop_is_refused(tmp_path: Path) -> None:
    from works.domain.errors import HarnessError

    with pytest.raises(HarnessError, match="no patch and no stop reason"):
        asyncio.run(FakeHarness(_trace(tmp_path, patch="")).propose(_request(tmp_path)))
