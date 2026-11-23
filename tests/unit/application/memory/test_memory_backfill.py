from __future__ import annotations

from datetime import UTC, datetime

from tests.unit.application.memory.test_memory import FakeTransport
from tests.unit.domain.test_evidence import fixed_evidence
from works.adapters.queue.store import Queue
from works.application.memory.backfill import backfill_runs
from works.application.memory.ppma import PpmaMemory
from works.config import WorksPaths
from works.domain.evidence import write_evidence
from works.domain.records import RunRecord, Source, SourceKind, StopReason, TaskState


def _task(paths: WorksPaths):
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="GH-BACKFILL", title="backfill me"),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(paths.root),
    )
    return task


def _run(paths: WorksPaths, task_id: str, run_id: str, *, with_evidence: bool) -> None:
    run_dir = paths.runs / run_id
    run_dir.mkdir(parents=True)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    record = RunRecord(
        run_id=run_id,
        task_id=task_id,
        flow="fix-issue",
        state=TaskState.PROVED,
        stop_reason=StopReason.COMPLETED,
        started_at=now,
        finished_at=now,
        tokens=1200,
        usd=0.012,
    )
    (run_dir / "run.json").write_text(record.model_dump_json(indent=2), encoding="utf-8")
    if with_evidence:
        evidence = fixed_evidence().model_copy(update={"task_id": task_id, "run_id": run_id})
        write_evidence(run_dir, evidence)


def test_backfill_reports_every_finished_run_without_a_rerun(paths) -> None:
    task = _task(paths)
    _run(paths, task.id, "r-backfill-1", with_evidence=True)
    transport = FakeTransport()
    memory = PpmaMemory(
        "http://ppma",
        transport=transport,
        owner_token="owner",  # noqa: S106 - a test token
    )

    entries = backfill_runs(paths, memory)

    assert [(entry.run_id, entry.status) for entry in entries] == [("r-backfill-1", "reported")]
    assert [call[0] for call in transport.calls] == ["PUT", "POST", "POST"]
    batch = transport.calls[-1][2]
    assert batch is not None
    first = batch["messages"][0]
    assert first["type"] == "works.run_finished"
    assert first["payload"]["task_id"] == task.id
    assert first["payload"]["run_id"] == "r-backfill-1"
    memory_events = [
        event for event in Queue(paths).events(task.id) if event.type == "memory.reported"
    ]
    assert len(memory_events) == 1
    assert memory_events[0].data["via"] == "backfill"

    backfill_runs(paths, memory)
    again = [event for event in Queue(paths).events(task.id) if event.type == "memory.reported"]
    assert len(again) == 1


def test_a_run_without_evidence_is_skipped_not_failed(paths) -> None:
    task = _task(paths)
    _run(paths, task.id, "r-no-evidence", with_evidence=False)

    entries = backfill_runs(paths, PpmaMemory("http://ppma", transport=FakeTransport()))

    assert [entry.status for entry in entries] == ["skipped"]
    assert entries[0].error == "no evidence.json"


def test_dry_run_sends_nothing(paths) -> None:
    task = _task(paths)
    _run(paths, task.id, "r-dry", with_evidence=True)
    transport = FakeTransport()

    entries = backfill_runs(
        paths,
        PpmaMemory("http://ppma", transport=transport),
        dry_run=True,
    )

    assert [entry.status for entry in entries] == ["dry-run"]
    assert transport.calls == []
