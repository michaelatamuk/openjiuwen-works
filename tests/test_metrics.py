from __future__ import annotations

from works.adapters.queue.ledger import Ledger
from works.adapters.queue.store import Queue
from works.application.observability.metrics import collect
from works.config import WorksPaths
from works.domain.records import LedgerRow, Source, SourceKind, TaskState


def make_task(queue: Queue) -> str:
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="GH-1", title="bug"),
        flow="fix-issue",
        product="openjiuwen",
        repo=".",
    )
    return task.id


def test_an_empty_factory_has_zero_metrics(paths: WorksPaths) -> None:
    metrics = collect(Queue(paths), Ledger(paths.ledger))
    assert metrics.tasks == 0
    assert metrics.human_touches == 0
    assert metrics.median_duration_ms is None


def test_human_touches_and_waiting_come_from_events(paths: WorksPaths) -> None:
    queue = Queue(paths)
    task_id = make_task(queue)
    queue.transition(task_id, TaskState.REPRODUCING)
    queue.transition(task_id, TaskState.REPRODUCED)
    queue.transition(task_id, TaskState.PLANNING)
    queue.append(task_id, "gate.decided", {"gate": "plan", "by": "human"})
    queue.transition(task_id, TaskState.PLAN_APPROVED)
    Ledger(paths.ledger).append(
        LedgerRow(
            task_id=task_id,
            run_id="r-1",
            state=TaskState.PLAN_APPROVED,
            tokens=100,
            usd=0.01,
        )
    )
    metrics = collect(queue, Ledger(paths.ledger))
    item = metrics.per_task[0]
    assert item.human_touches == 1
    assert item.waiting_ms >= 0
    assert item.tokens == 100
    assert metrics.tokens == 100
    assert metrics.usd == 0.01


def test_an_auto_approved_run_counts_as_without_human(paths: WorksPaths) -> None:
    queue = Queue(paths)
    task_id = make_task(queue)
    queue.append(task_id, "attempt.started", {})
    queue.append(task_id, "gate.decided", {"gate": "plan", "by": "flow"})
    metrics = collect(queue, Ledger(paths.ledger))
    assert metrics.human_touches == 0
    assert metrics.runs_without_human == 1
