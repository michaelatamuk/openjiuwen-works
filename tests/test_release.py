from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime

import pytest

from tests.test_evidence import fixed_evidence
from works.cli import main
from works.config import WorksPaths
from works.errors import ConfigError
from works.evidence import write_evidence
from works.queue import Queue
from works.records import RunRecord, Source, SourceKind, StopReason, Task, TaskState
from works.release import approve_release, release_packet


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
