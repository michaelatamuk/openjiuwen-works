from __future__ import annotations

from datetime import UTC, datetime

from tests.test_evidence import fixed_evidence
from works.config import WorksPaths
from works.evidence import write_evidence
from works.queue import Queue
from works.records import RunRecord, Source, SourceKind, StopReason, Task, TaskState
from works.release import release_packet


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
    queue.append(
        task.id,
        "gate.decided",
        {"gate": "release", "by": "cli", "commit": "abc1234"},
    )

    packet = release_packet(paths, task.id)

    assert packet.ready is True
    assert packet.commit == "abc1234"
    assert packet.proof_sha256
    assert packet.blockers == []


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
