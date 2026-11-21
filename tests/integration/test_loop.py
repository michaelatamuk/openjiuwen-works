from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from works.errors import StateError
from works.flakes import add_flake
from works.ledger import Ledger
from works.quarantine import QuarantineError
from works.queue import Queue
from works.records import Budget, LedgerRow, StopReason, TaskKind, TaskState
from works.scenarios import judge
from works.supervisor import Supervisor

pytestmark = pytest.mark.integration


def run(supervisor: Supervisor, task_id: str, scenario_set: Path, **kwargs):
    return asyncio.run(supervisor.run(task_id, scenario_set=scenario_set, **kwargs))


def evidence(paths, record) -> dict:
    return json.loads((paths.run_dir(record.run_id) / "evidence.json").read_text(encoding="utf-8"))


def test_the_whole_loop_proves_a_fix(paths, submit, scenario_set, make_supervisor, repo) -> None:
    task = submit()
    record = run(make_supervisor("fix-add"), task.id, scenario_set, approve_plan=True)

    proof = evidence(paths, record)
    test = proof.get("test") or {}
    detail = (test.get("exit_code"), test.get("stdout_tail"), test.get("stderr_tail"))
    assert record.stop_reason is StopReason.COMPLETED, detail
    assert record.state is TaskState.PROVED
    assert record.tokens == 1200
    assert record.usd == pytest.approx(0.012)
    assert record.base_commit == repo.head()

    stored = Queue(paths).load(task.id)
    assert stored.state is TaskState.PROVED
    Queue(paths).verify_projection(task.id)

    proof = evidence(paths, record)
    assert proof["verdict"]["allow"] is True
    assert proof["verdict"]["p0_failed"] == []
    assert proof["files_changed"] == ["calc/core.py"]
    assert proof["policy"]["ok"] is True
    assert proof["reproduce"]["exit_code"] != 0
    assert proof["test"]["exit_code"] == 0
    assert len(proof["proof_sha256"]) == 64

    page = (paths.run_dir(record.run_id) / "evidence.md").read_text(encoding="utf-8")
    assert "**ALLOW**" in page
    assert "| PASS |" in page
    assert "| FAIL |" not in page
    assert "calc/core.py" in page

    rows = Ledger(paths.ledger).rows()
    assert len(rows) == 1
    assert rows[0].verdict == "allow"
    assert rows[0].state is TaskState.PROVED
    assert not repo.is_dirty(), "the product repository is never modified in place"


def test_the_plan_gate_stops_and_then_resumes(paths, submit, scenario_set, make_supervisor) -> None:
    task = submit()
    supervisor = make_supervisor("fix-add")
    first = run(supervisor, task.id, scenario_set, approve_plan=False)
    assert first.state is TaskState.PLANNING
    assert first.stop_reason is StopReason.NEEDS_PLAN_APPROVAL
    assert Queue(paths).load(task.id).state is TaskState.PLANNING

    second = run(make_supervisor("fix-add"), task.id, scenario_set, approve_plan=True)
    assert second.state is TaskState.PROVED
    assert second.stop_reason is StopReason.COMPLETED
    events = Queue(paths).events(task.id)
    assert sum(1 for event in events if event.type == "gate.decided") == 1


def test_a_preapproved_plan_runs_without_the_flag(
    paths, submit, scenario_set, make_supervisor
) -> None:
    from works.records import TaskState

    task = submit()
    first = run(make_supervisor("fix-add"), task.id, scenario_set, approve_plan=False)
    assert first.stop_reason is StopReason.NEEDS_PLAN_APPROVAL
    queue = Queue(paths)
    queue.transition(task.id, TaskState.PLAN_APPROVED)
    plan = [event for event in queue.events(task.id) if event.type == "plan.drafted"][-1].data
    queue.append(
        task.id,
        "gate.decided",
        {
            "gate": "plan",
            "decision": "approved",
            "commit": plan["base_commit"],
            "checks_sha": plan["checks_sha"],
        },
    )
    second = run(make_supervisor("fix-add"), task.id, scenario_set, approve_plan=False)
    assert second.state is TaskState.PROVED
    assert second.stop_reason is StopReason.COMPLETED


def test_the_wall_clock_budget_is_enforced(paths, submit, scenario_set, make_supervisor) -> None:
    task = submit(budget=Budget(tokens=1_000_000, usd=100.0, wall_minutes=0))
    record = run(make_supervisor("fix-add"), task.id, scenario_set, approve_plan=True)
    assert record.state is TaskState.BLOCKED
    assert record.stop_reason is StopReason.BUDGET_EXCEEDED


def test_not_reproducible_blocks(paths, submit, scenario_set, make_supervisor, make_repo) -> None:
    fixed = make_repo(fixed=True, name="fixed")
    task = submit(repo_path=fixed.path)
    record = run(make_supervisor("fix-add"), task.id, scenario_set, approve_plan=True)
    assert record.state is TaskState.BLOCKED
    assert record.stop_reason is StopReason.NOT_REPRODUCIBLE
    assert Queue(paths).load(task.id).state is TaskState.BLOCKED
    proof = evidence(paths, record)
    assert proof["reproduce"]["exit_code"] == 0
    assert proof["verdict"] is None


def test_a_test_edit_is_refused_before_any_command(
    paths, submit, scenario_set, make_supervisor
) -> None:
    task = submit()
    record = run(make_supervisor("fix-add-test-edit"), task.id, scenario_set, approve_plan=True)
    assert record.state is TaskState.BLOCKED
    assert record.stop_reason is StopReason.POLICY_VIOLATION
    proof = evidence(paths, record)
    assert proof["policy"]["ok"] is False
    assert any("tests/test_core.py" in item["path"] for item in proof["policy"]["violations"])
    assert proof["test"] is None
    assert proof["diff"] == ""


def test_a_check_edit_is_refused_for_a_normal_fix(
    paths, submit, scenario_set, make_supervisor
) -> None:
    task = submit()
    record = run(make_supervisor("fix-check-edit"), task.id, scenario_set, approve_plan=True)
    assert record.state is TaskState.BLOCKED
    assert record.stop_reason is StopReason.POLICY_VIOLATION
    proof = evidence(paths, record)
    assert proof["policy"]["ok"] is False
    assert any("check-change" in item["reason"] for item in proof["policy"]["violations"])


def test_a_check_change_task_may_edit_checks(paths, submit, scenario_set, make_supervisor) -> None:
    task = submit(task_kind=TaskKind.CHECK_CHANGE)
    record = run(make_supervisor("fix-check-edit"), task.id, scenario_set, approve_plan=True)
    assert record.stop_reason is StopReason.COMPLETED
    proof = evidence(paths, record)
    assert proof["task_kind"] == "check-change"
    assert proof["policy"]["ok"] is True


def test_an_active_flake_blocks_the_verdict(paths, submit, scenario_set, make_supervisor) -> None:
    task = submit()
    add_flake(
        paths,
        task_id=task.id,
        scenario_id="add-negative",
        owner="michael",
        reason="times out on Windows",
    )
    record = run(make_supervisor("fix-add"), task.id, scenario_set, approve_plan=True)
    assert record.state is TaskState.BLOCKED
    assert record.stop_reason is StopReason.FLAKY_TEST
    assert any(event.type == "flake" for event in Queue(paths).events(task.id))


def test_a_blocking_challenge_stops_the_change(
    paths, submit, scenario_set, make_supervisor
) -> None:
    task = submit()
    record = run(
        make_supervisor("fix-add-challenge-block"), task.id, scenario_set, approve_plan=True
    )
    assert record.state is TaskState.BLOCKED
    assert record.stop_reason is StopReason.CHALLENGE_FAILED
    proof = evidence(paths, record)
    assert proof["challenge"]["allow"] is False
    assert "negative inputs" in " ".join(proof["challenge"]["concerns"])
    assert proof["verdict"] is None


def test_a_sneaky_patch_fails_the_holdout(paths, submit, scenario_set, make_supervisor) -> None:
    task = submit()
    record = run(make_supervisor("fix-add-sneaky"), task.id, scenario_set, approve_plan=True)
    assert record.state is TaskState.BLOCKED
    assert record.stop_reason is StopReason.VERDICT_FAILED
    proof = evidence(paths, record)
    assert proof["test"]["exit_code"] == 0, "the visible tests pass"
    assert proof["verdict"]["allow"] is False
    assert proof["verdict"]["p0_failed"] == ["add-negative"]
    assert any(
        item["id"] == "add-negative" and item["passed"] is False
        for item in proof["verdict"]["outcomes"]
    )


def test_the_harness_may_abstain(paths, submit, scenario_set, make_supervisor) -> None:
    task = submit()
    record = run(make_supervisor("cannot-fix"), task.id, scenario_set, approve_plan=True)
    assert record.state is TaskState.BLOCKED
    assert record.stop_reason is StopReason.HARNESS_FAILED
    assert record.tokens == 300


def test_the_token_budget_is_enforced(paths, submit, scenario_set, make_supervisor) -> None:
    task = submit(budget=Budget(tokens=100, usd=1.0))
    record = run(make_supervisor("fix-add"), task.id, scenario_set, approve_plan=True)
    assert record.state is TaskState.BLOCKED
    assert record.stop_reason is StopReason.BUDGET_EXCEEDED


def test_a_quarantine_file_inside_the_repository_is_refused(
    paths, submit, scenario_set, make_supervisor, repo
) -> None:
    inside = repo.path / "quarantine.json"
    inside.write_text('{"paths": ["calc/core.py"]}', encoding="utf-8")
    task = submit()
    with pytest.raises(QuarantineError):
        run(
            make_supervisor("fix-add"),
            task.id,
            scenario_set,
            approve_plan=True,
            quarantine=inside,
        )


def test_a_quarantine_list_outside_the_repository_denies_its_paths(
    paths, submit, scenario_set, make_supervisor, tmp_path
) -> None:
    outside = tmp_path / "quarantine.json"
    outside.write_text('{"schema_version": 1, "paths": ["calc/core.py"]}', encoding="utf-8")
    task = submit()
    record = run(
        make_supervisor("fix-add"),
        task.id,
        scenario_set,
        approve_plan=True,
        quarantine=outside,
    )
    assert record.stop_reason is StopReason.POLICY_VIOLATION


def test_a_terminal_task_cannot_run_again(paths, submit, scenario_set, make_supervisor) -> None:
    task = submit()
    run(make_supervisor("fix-add"), task.id, scenario_set, approve_plan=True)
    with pytest.raises(StateError):
        run(make_supervisor("fix-add"), task.id, scenario_set, approve_plan=True)


def test_a_dirty_repository_is_refused(paths, submit, scenario_set, make_supervisor, repo) -> None:
    (repo.path / "calc" / "core.py").write_text("# dirty\n", encoding="utf-8", newline="\n")
    task = submit()
    record = run(make_supervisor("fix-add"), task.id, scenario_set, approve_plan=True)
    assert record.state is TaskState.BLOCKED
    assert record.stop_reason is StopReason.CONFLICT


def test_escape_window_and_revert(paths, submit) -> None:
    queue = Queue(paths)
    task = submit()
    for target in (
        TaskState.REPRODUCING,
        TaskState.REPRODUCED,
        TaskState.PLANNING,
        TaskState.PLAN_APPROVED,
        TaskState.BUILDING,
        TaskState.CHECKING,
        TaskState.PROVED,
        TaskState.RELEASING,
        TaskState.RELEASED,
        TaskState.REVERTED,
    ):
        queue.transition(task.id, target)
    assert queue.load(task.id).state is TaskState.REVERTED
    Ledger(paths.ledger).append(
        LedgerRow(task_id=task.id, run_id="r-1", state=TaskState.REVERTED, escape=True)
    )
    row = Ledger(paths.ledger).rows()[-1]
    assert row.escape is True
    with pytest.raises(StateError):
        queue.transition(task.id, TaskState.QUEUED)


def test_judge_uses_the_same_rule_as_the_supervisor() -> None:
    from works.records import Priority, ScenarioOutcome

    outcomes = [
        ScenarioOutcome(
            id="a",
            priority=Priority.P0,
            weight=1.0,
            passed=False,
            exit_code=1,
            duration_ms=1,
            output_sha256="0" * 64,
        )
    ]
    assert judge(outcomes, run_id="r").allow is False
