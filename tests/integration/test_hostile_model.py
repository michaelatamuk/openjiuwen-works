"""A model that talks like an approver must not become one."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from works.adapters.harness.base import ProposalRequest
from works.adapters.harness.fake import FakeHarness
from works.adapters.queue.store import Queue
from works.application.supervisor import Supervisor
from works.domain.errors import HarnessError
from works.domain.records import StopReason, TaskState

pytestmark = pytest.mark.integration


def run(supervisor: Supervisor, task_id: str, scenario_set: Path, **kwargs):
    return asyncio.run(supervisor.run(task_id, scenario_set=scenario_set, **kwargs))


def evidence(paths, record) -> dict:
    return json.loads((paths.run_dir(record.run_id) / "evidence.json").read_text(encoding="utf-8"))


def test_model_claims_cannot_open_the_plan_gate(
    paths, submit, scenario_set, make_supervisor
) -> None:
    task = submit()
    record = run(make_supervisor("hostile-claims"), task.id, scenario_set, approve_plan=False)

    assert record.state is TaskState.PLANNING
    assert record.stop_reason is StopReason.NEEDS_PLAN_APPROVAL
    events = [event.type for event in Queue(paths).events(task.id)]
    assert "gate.decided" not in events
    assert Queue(paths).load(task.id).state is not TaskState.RELEASED


def test_model_claims_do_not_release_the_task(paths, submit, scenario_set, make_supervisor) -> None:
    task = submit()
    record = run(make_supervisor("hostile-claims"), task.id, scenario_set, approve_plan=True)

    assert record.state is TaskState.PROVED, "a model note cannot open gate 2"
    gate = [
        event
        for event in Queue(paths).events(task.id)
        if event.type == "gate.decided" and event.data.get("gate") == "release"
    ]
    assert gate == []


def test_model_claims_do_not_override_a_failed_holdout(
    paths, submit, scenario_set, make_supervisor
) -> None:
    task = submit()
    record = run(make_supervisor("hostile-sneaky"), task.id, scenario_set, approve_plan=True)

    proof = evidence(paths, record)
    assert record.state is TaskState.BLOCKED
    assert record.stop_reason is StopReason.VERDICT_FAILED
    assert proof["test"]["exit_code"] == 0, "the visible tests still pass"
    assert proof["verdict"]["allow"] is False
    assert proof["verdict"]["p0_failed"] == ["add-negative"]
    assert "RELEASE APPROVED" not in json.dumps(proof), (
        "model text is never promoted into the proof"
    )
    assert "PLAN APPROVED" not in json.dumps(proof)


def test_an_invalid_trace_fails_closed(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(HarnessError, match="not valid JSON"):
        FakeHarness(broken)

    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text('{"schema_version": 1}', encoding="utf-8")
    with pytest.raises(HarnessError, match="not a valid trace"):
        FakeHarness(incomplete)


def test_a_trace_without_a_patch_or_stop_reason_fails_closed(tmp_path: Path) -> None:
    trace = tmp_path / "empty.json"
    trace.write_text(
        json.dumps({"schema_version": 1, "name": "empty", "notes": ["trust me, it works"]}),
        encoding="utf-8",
    )

    with pytest.raises(HarnessError, match="no patch and no stop reason"):
        asyncio.run(
            FakeHarness(trace).propose(
                ProposalRequest(
                    task_id="t-1",
                    source_ref="GH-1",
                    title="add subtracts",
                    worktree=tmp_path,
                    base_commit="0" * 40,
                )
            )
        )
