"""A manager-facing report over the queue, the runs and the ledger.

Pure read: it never writes to the home and never calls a model. The numbers are the ones the deck
promises: time from report to release, cost per released change, what the gates decided, how often a
reporter reopened a task, and how many escapes were seen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from works.adapters.queue.store import Queue
from works.config.paths import WorksPaths
from works.domain.evidence import Evidence
from works.domain.records import RunRecord


@dataclass(frozen=True)
class TimeStats:
    median_min: float | None = None
    p90_min: float | None = None
    samples: int = 0


@dataclass(frozen=True)
class Report:
    days: int
    generated_at: datetime
    tasks: int = 0
    by_state: dict[str, int] = field(default_factory=dict)
    released: int = 0
    time_to_release: TimeStats = field(default_factory=TimeStats)
    runs: int = 0
    total_usd: float = 0.0
    per_released_usd: float | None = None
    gates: dict[str, dict[str, int]] = field(default_factory=dict)
    reopens: int = 0
    cve_tasks: int = 0
    cve_released: int = 0
    escapes: int = 0
    rework: int = 0
    stop_reasons: dict[str, int] = field(default_factory=dict)


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(len(ordered) - 1, low + 1)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _latest_evidence(paths: WorksPaths) -> dict[str, Evidence]:
    """The newest evidence record per task; cost is reported for the latest attempt."""
    latest: dict[str, Evidence] = {}
    mtimes: dict[str, float] = {}
    for path in paths.runs.glob("*/evidence.json"):
        try:
            evidence = Evidence.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        mtime = path.stat().st_mtime
        if mtime > mtimes.get(evidence.task_id, -1.0):
            latest[evidence.task_id] = evidence
            mtimes[evidence.task_id] = mtime
    return latest


def _run_records(paths: WorksPaths) -> list[RunRecord]:
    records: list[RunRecord] = []
    for path in paths.runs.glob("*/run.json"):
        try:
            records.append(RunRecord.model_validate_json(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return records


def build_report(paths: WorksPaths, *, days: int = 30, now: datetime | None = None) -> Report:
    moment = now or datetime.now(tz=UTC)
    cutoff = moment - timedelta(days=days)
    queue = Queue(paths)
    tasks = [task for task in queue.list_tasks() if task.created_at >= cutoff]
    by_id = {task.id: task for task in tasks}
    by_state: dict[str, int] = {}
    released = 0
    durations: list[float] = []
    reopens = 0
    cve_tasks = 0
    cve_released = 0
    escapes = 0
    rework = 0
    gates: dict[str, dict[str, int]] = {
        "plan": {"approved": 0, "changes_requested": 0, "rejected": 0},
        "release": {"approved": 0, "changes_requested": 0, "rejected": 0},
    }
    for task in tasks:
        by_state[task.state.value] = by_state.get(task.state.value, 0) + 1
        if task.state.value == "released":
            released += 1
        if task.source.channel == "cve":
            cve_tasks += 1
            if task.state.value == "released":
                cve_released += 1
        first_release: datetime | None = None
        for event in queue.events(task.id):
            if event.type == "gate.decided":
                gate = str(event.data.get("gate") or "")
                decision = str(event.data.get("decision") or "")
                if gate in gates and decision in gates[gate]:
                    gates[gate][decision] += 1
                if gate == "release" and decision == "approved" and first_release is None:
                    first_release = event.ts
            elif event.type == "reporter.replied" and event.data.get("reopened") is True:
                reopens += 1
            elif event.type == "escape.detected":
                escapes += 1
            elif event.type == "rework.detected":
                rework += 1
        if first_release is not None:
            minutes = (first_release - task.created_at).total_seconds() / 60.0
            if minutes >= 0:
                durations.append(minutes)

    evidence = _latest_evidence(paths)
    total_usd = round(sum(item.usd for task_id, item in evidence.items() if task_id in by_id), 4)
    released_usd = round(
        sum(item.usd for task_id, item in evidence.items() if task_id in by_id and item.usd),
        4,
    )
    per_released = round(released_usd / released, 4) if released else None

    records = [record for record in _run_records(paths) if record.task_id in by_id]
    stops: dict[str, int] = {}
    for record in records:
        stops[record.stop_reason.value] = stops.get(record.stop_reason.value, 0) + 1

    return Report(
        days=days,
        generated_at=moment,
        tasks=len(tasks),
        by_state=dict(sorted(by_state.items())),
        released=released,
        time_to_release=TimeStats(
            median_min=_percentile(durations, 0.5),
            p90_min=_percentile(durations, 0.9),
            samples=len(durations),
        ),
        runs=len(records),
        total_usd=total_usd,
        per_released_usd=per_released,
        gates=gates,
        reopens=reopens,
        cve_tasks=cve_tasks,
        cve_released=cve_released,
        escapes=escapes,
        rework=rework,
        stop_reasons=dict(sorted(stops.items())),
    )


def as_dict(report: Report) -> dict[str, object]:
    return {
        "days": report.days,
        "generated_at": report.generated_at.isoformat(),
        "tasks": report.tasks,
        "by_state": report.by_state,
        "released": report.released,
        "time_to_release": {
            "median_min": report.time_to_release.median_min,
            "p90_min": report.time_to_release.p90_min,
            "samples": report.time_to_release.samples,
        },
        "runs": report.runs,
        "total_usd": report.total_usd,
        "per_released_usd": report.per_released_usd,
        "gates": report.gates,
        "reopens": report.reopens,
        "cve_tasks": report.cve_tasks,
        "cve_released": report.cve_released,
        "escapes": report.escapes,
        "rework": report.rework,
        "stop_reasons": report.stop_reasons,
    }


def format_minutes(value: float | None) -> str:
    if value is None:
        return "not enough data"
    minutes = round(value)
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} h {rest:02d} min"
    days, hours = divmod(hours, 24)
    return f"{days} d {hours} h"
