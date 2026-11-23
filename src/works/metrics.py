"""Attention and cost metrics derived from events and the ledger. Never from agent prose."""

from __future__ import annotations

import statistics
from datetime import datetime

from pydantic import BaseModel, Field

from .escapes import EscapeReport
from .ledger import Ledger
from .queue import Queue
from .records import Event, Task, TaskState

FINISHED = {TaskState.PROVED, TaskState.BLOCKED, TaskState.RELEASED, TaskState.REVERTED}


class TaskMetric(BaseModel):
    task_id: str
    state: TaskState
    duration_ms: int
    human_touches: int
    waiting_ms: int
    had_run: bool
    tokens: int = 0
    usd: float = 0.0


class FactoryMetrics(BaseModel):
    schema_version: int = 1
    tasks: int
    proved: int
    blocked: int
    human_touches: int
    runs_without_human: int
    waiting_ms: int
    median_duration_ms: int | None
    tokens: int
    usd: float
    escapes: int = 0
    rework: int = 0
    per_task: list[TaskMetric] = Field(default_factory=list)


def _waiting_ms(events: list[Event]) -> int:
    entered: datetime | None = None
    total = 0
    for event in events:
        if event.type != "state.changed":
            continue
        if event.data.get("to") == TaskState.PLANNING.value:
            entered = event.ts
        elif entered is not None and event.data.get("from") == TaskState.PLANNING.value:
            total += int((event.ts - entered).total_seconds() * 1000)
            entered = None
    return total


def task_metric(task: Task, events: list[Event], *, tokens: int, usd: float) -> TaskMetric:
    human = sum(
        1
        for event in events
        if event.type == "gate.decided" and event.data.get("by") in ("human", "cli")
    )
    return TaskMetric(
        task_id=task.id,
        state=task.state,
        duration_ms=int((events[-1].ts - events[0].ts).total_seconds() * 1000) if events else 0,
        human_touches=human,
        waiting_ms=_waiting_ms(events),
        had_run=any(event.type == "attempt.started" for event in events),
        tokens=tokens,
        usd=usd,
    )


def collect(
    queue: Queue,
    ledger: Ledger,
    *,
    escape_report: EscapeReport | None = None,
) -> FactoryMetrics:
    totals: dict[str, tuple[int, float]] = {}
    for row in ledger.rows():
        old_tokens, old_usd = totals.get(row.task_id, (0, 0.0))
        totals[row.task_id] = (old_tokens + (row.tokens or 0), old_usd + (row.usd or 0.0))
    per_task: list[TaskMetric] = []
    for task in queue.list_tasks():
        tokens, usd = totals.get(task.id, (0, 0.0))
        per_task.append(task_metric(task, queue.events(task.id), tokens=tokens, usd=usd))
    finished = [item for item in per_task if item.state in FINISHED]
    return FactoryMetrics(
        tasks=len(per_task),
        proved=sum(1 for item in per_task if item.state is TaskState.PROVED),
        blocked=sum(1 for item in per_task if item.state is TaskState.BLOCKED),
        human_touches=sum(item.human_touches for item in per_task),
        runs_without_human=sum(1 for item in per_task if item.had_run and item.human_touches == 0),
        waiting_ms=sum(item.waiting_ms for item in per_task),
        median_duration_ms=(
            int(statistics.median(item.duration_ms for item in finished)) if finished else None
        ),
        tokens=sum(item.tokens for item in per_task),
        usd=round(sum(item.usd for item in per_task), 6),
        escapes=escape_report.escapes if escape_report else 0,
        rework=len(escape_report.rework) if escape_report else 0,
        per_task=per_task,
    )
