from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta

import pytest

from tests.unit.domain.test_evidence import fixed_evidence
from works.adapters.queue.store import Queue
from works.application.delivery.release import (
    _expired,
    approve_release,
    decide_release,
    owner_approved,
    release_packet,
)
from works.config import WorksPaths
from works.domain.errors import ConfigError
from works.domain.evidence import write_evidence
from works.domain.records import RunRecord, Source, SourceKind, StopReason, Task, TaskState
from works.interfaces.cli.main import main


def _proved(paths: WorksPaths) -> Task:
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="GH-RELEASE", title="release me"),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(paths.root),
    )
    for state in (
        TaskState.REPRODUCING,
        TaskState.REPRODUCED,
        TaskState.PLANNING,
        TaskState.PLAN_APPROVED,
        TaskState.BUILDING,
        TaskState.CHECKING,
        TaskState.PROVED,
    ):
        queue.transition(task.id, state)
    return queue.load(task.id)


def _run(paths: WorksPaths, task: Task) -> str:
    run_id = "r-release"
    evidence = fixed_evidence().model_copy(
        update={
            "task_id": task.id,
            "run_id": run_id,
            "base_commit": "abc1234",
            "state": TaskState.PROVED,
        }
    )
    run_dir = paths.runs / run_id
    run_dir.mkdir(parents=True)
    write_evidence(run_dir, evidence)
    now = datetime.now(tz=UTC)
    record = RunRecord(
        run_id=run_id,
        task_id=task.id,
        flow="fix-issue",
        state=TaskState.PROVED,
        stop_reason=StopReason.COMPLETED,
        base_commit="abc1234",
        started_at=now,
        finished_at=now,
    )
    (run_dir / "run.json").write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return run_id


def test_a_proved_task_with_both_gates_is_release_ready(paths) -> None:
    task = _proved(paths)
    _run(paths, task)
    queue = Queue(paths)
    queue.append(
        task.id,
        "gate.decided",
        {"gate": "plan", "by": "cli", "commit": "abc1234"},
    )
    pending = release_packet(paths, task.id)
    queue.append(
        task.id,
        "gate.decided",
        {
            "gate": "release",
            "by": "cli",
            "commit": "abc1234",
            "proof_sha256": pending.proof_sha256,
        },
    )

    packet = release_packet(paths, task.id)

    assert packet.ready is True
    assert packet.commit == "abc1234"
    assert packet.proof_sha256
    assert packet.blockers == []


def test_a_release_bound_to_another_proof_blocks_the_packet(paths) -> None:
    task = _proved(paths)
    _run(paths, task)
    queue = Queue(paths)
    queue.append(
        task.id,
        "gate.decided",
        {"gate": "plan", "by": "cli", "commit": "abc1234"},
    )
    queue.append(
        task.id,
        "gate.decided",
        {
            "gate": "release",
            "by": "cli",
            "commit": "abc1234",
            "proof_sha256": "deadbeef",
        },
    )

    packet = release_packet(paths, task.id)

    assert packet.ready is False
    assert "release approval is bound to another proof" in packet.blockers


def test_a_missing_release_gate_blocks_the_packet(paths) -> None:
    task = _proved(paths)
    _run(paths, task)
    Queue(paths).append(
        task.id,
        "gate.decided",
        {"gate": "plan", "by": "cli", "commit": "abc1234"},
    )

    packet = release_packet(paths, task.id)

    assert packet.ready is False
    assert "release gate has no human approval" in packet.blockers


def test_gate_two_transitions_the_task_and_is_idempotent(paths) -> None:
    task = _proved(paths)
    _run(paths, task)
    Queue(paths).append(
        task.id,
        "gate.decided",
        {"gate": "plan", "by": "cli", "commit": "abc1234"},
    )

    released, packet, created = approve_release(paths, task.id)

    assert created is True
    assert released.state is TaskState.RELEASED
    assert packet.released is True
    assert packet.commit == "abc1234"
    assert (paths.runs / "r-release" / "release.json").exists()

    again, packet_again, created_again = approve_release(paths, task.id)

    assert created_again is False
    assert again.state is TaskState.RELEASED
    assert packet_again.release_gate == packet.release_gate
    events = [event for event in Queue(paths).events(task.id) if event.type == "gate.decided"]
    assert len([event for event in events if event.data.get("gate") == "release"]) == 1


def test_gate_two_refuses_an_unready_packet(paths) -> None:
    task = _proved(paths)
    _run(paths, task)

    with pytest.raises(ConfigError, match="plan gate has no human approval"):
        approve_release(paths, task.id)

    assert Queue(paths).load(task.id).state is TaskState.PROVED


def test_gate_two_refuses_a_plan_bound_to_another_commit(paths) -> None:
    task = _proved(paths)
    _run(paths, task)
    Queue(paths).append(
        task.id,
        "gate.decided",
        {"gate": "plan", "by": "cli", "commit": "deadbee"},
    )

    with pytest.raises(ConfigError, match="plan approval is bound to another commit"):
        approve_release(paths, task.id)


def test_a_released_packet_still_has_no_blockers(paths) -> None:
    task = _proved(paths)
    _run(paths, task)
    Queue(paths).append(
        task.id,
        "gate.decided",
        {"gate": "plan", "by": "cli", "commit": "abc1234"},
    )

    approve_release(paths, task.id)

    packet = release_packet(paths, task.id)
    assert packet.ready is True
    assert packet.released is True


def test_gate_two_refuses_a_task_that_never_reached_proof(paths) -> None:
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="GH-NOT-PROVED", title="not proved"),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(paths.root),
    )

    with pytest.raises(ConfigError, match="not proved"):
        approve_release(paths, task.id)


def _invoke(paths: WorksPaths, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(["--home", str(paths.root), *args])
    return code, out.getvalue(), err.getvalue()


def test_the_cli_opens_gate_two(paths) -> None:
    task = _proved(paths)
    _run(paths, task)
    Queue(paths).append(
        task.id,
        "gate.decided",
        {"gate": "plan", "by": "cli", "commit": "abc1234"},
    )

    code, out, err = _invoke(paths, "approve", task.id, "--gate", "release", "--json")

    assert code == 0, err
    body = json.loads(out.strip().splitlines()[-1])
    assert body["created"] is True
    assert body["task"]["state"] == "released"
    assert body["release"]["released"] is True


def test_the_cli_reports_release_blockers_with_exit_8(paths) -> None:
    task = _proved(paths)
    _run(paths, task)

    code, out, _ = _invoke(paths, "approve", task.id, "--gate", "release", "--json")

    assert code == 8
    body = json.loads(out.strip().splitlines()[-1])
    assert body["ok"] is False
    assert "plan gate has no human approval" in body["blockers"]


def test_the_cli_is_idempotent_on_gate_two(paths) -> None:
    task = _proved(paths)
    _run(paths, task)
    Queue(paths).append(
        task.id,
        "gate.decided",
        {"gate": "plan", "by": "cli", "commit": "abc1234"},
    )
    _invoke(paths, "approve", task.id, "--gate", "release")

    code, out, err = _invoke(paths, "approve", task.id, "--gate", "release")

    assert code == 0, err
    assert "already released" in out


def _ready(paths) -> Task:
    task = _proved(paths)
    _run(paths, task)
    queue = Queue(paths)
    queue.append(task.id, "gate.decided", {"gate": "plan", "by": "cli", "commit": "abc1234"})
    return queue.load(task.id)


def test_a_hold_needs_a_comment_and_keeps_the_task_proved(paths) -> None:
    task = _ready(paths)

    with pytest.raises(ConfigError, match="needs a comment"):
        decide_release(paths, task.id, decision="changes_requested")

    held, _packet, created = decide_release(
        paths, task.id, decision="changes_requested", comment="show the deploy target", by="michael"
    )

    assert held.state is TaskState.PROVED
    assert created is False
    events = [event for event in Queue(paths).events(task.id) if event.type == "gate.decided"]
    assert events[-1].data["decision"] == "changes_requested"
    assert events[-1].data["comment"] == "show the deploy target"


def test_a_reject_blocks_the_task(paths) -> None:
    task = _ready(paths)

    with pytest.raises(ConfigError, match="needs a comment"):
        decide_release(paths, task.id, decision="rejected")

    rejected, _packet, _created = decide_release(
        paths, task.id, decision="rejected", comment="wrong release window", by="michael"
    )

    assert rejected.state is TaskState.BLOCKED


def test_an_agent_cannot_release(paths) -> None:
    task = _ready(paths)

    with pytest.raises(ConfigError, match="agent cannot"):
        decide_release(paths, task.id, by="builder")


def test_quorum_needs_a_second_person(paths, monkeypatch) -> None:
    monkeypatch.setenv("WORKS_REQUIRE_QUORUM", "1")
    task = _ready(paths)

    first, _packet, created = decide_release(paths, task.id, by="michael", device="laptop")
    assert first.state is TaskState.PROVED
    assert created is False

    second, _packet, created = decide_release(paths, task.id, by="michael", device="phone")
    assert second.state is TaskState.RELEASED
    assert created is True


def test_a_blocked_packet_names_its_codes(paths) -> None:
    task = _proved(paths)
    _run(paths, task)

    packet = release_packet(paths, task.id)

    codes = {item["code"] for item in packet.blocker_codes}
    assert "plan_gate_missing" in codes
    assert "release_gate_missing" in codes


def test_high_risk_owner_approval_is_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("WORKS_REQUIRE_OWNER_APPROVAL", raising=False)
    assert owner_approved("high", ["michael"], "someone") is True

    monkeypatch.setenv("WORKS_REQUIRE_OWNER_APPROVAL", "1")
    assert owner_approved("low", ["michael"], "someone") is True
    assert owner_approved("high", ["michael"], "michael") is True
    assert owner_approved("high", ["michael"], "someone") is False


def test_a_release_approval_expires() -> None:
    past = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat()
    future = (datetime.now(tz=UTC) + timedelta(hours=1)).isoformat()

    assert _expired({"expires_at": past}) is True
    assert _expired({"expires_at": future}) is False
    assert _expired({}) is False
