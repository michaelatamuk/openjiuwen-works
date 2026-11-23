"""Plan evaluation: compare plan modes and their outcomes across stored tasks."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from works.adapters.queue.store import Queue
from works.application.planning.service import PlanStatus, PlanStore, PlanVersion
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError
from works.domain.records import RunRecord


class PlanEvalRow(BaseModel):
    task_id: str
    plan_id: str
    version: int
    mode: str
    status: str
    validation_ok: bool | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    critic_allow: bool | None = None
    critic_score: float | None = None
    planner_tokens: int = 0
    planner_usd: float = 0.0
    approved: bool = False
    run_state: str | None = None
    run_stop_reason: str | None = None
    run_plan_id: str | None = None
    run_plan_hash: str | None = None


def _latest_runs(paths: WorksPaths) -> dict[str, RunRecord]:
    latest: dict[str, RunRecord] = {}
    if not paths.runs.exists():
        return latest
    for path in paths.runs.glob("*/run.json"):
        try:
            record = RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        current = latest.get(record.task_id)
        if current is None or record.started_at >= current.started_at:
            latest[record.task_id] = record
    return latest


def _row(plan: PlanVersion, run: RunRecord | None) -> PlanEvalRow:
    validation = plan.validation
    critique = plan.critique
    return PlanEvalRow(
        task_id=plan.task_id,
        plan_id=plan.plan_id,
        version=plan.version,
        mode=plan.provenance.mode,
        status=plan.status.value,
        validation_ok=validation.ok if validation is not None else None,
        errors=validation.errors if validation is not None else [],
        warnings=validation.warnings if validation is not None else [],
        critic_allow=critique.allow if critique is not None else None,
        critic_score=critique.score if critique is not None else None,
        planner_tokens=plan.provenance.tokens,
        planner_usd=plan.provenance.usd,
        approved=plan.status in (PlanStatus.APPROVED, PlanStatus.FROZEN) or bool(plan.approved_by),
        run_state=run.state.value if run is not None else None,
        run_stop_reason=run.stop_reason.value if run is not None else None,
        run_plan_id=run.plan_id if run is not None else None,
        run_plan_hash=run.plan_hash if run is not None else None,
    )


def evaluate(paths: WorksPaths, task_id: str | None = None) -> dict[str, Any]:
    queue = Queue(paths)
    tasks = [queue.load(task_id)] if task_id else queue.list_tasks()
    runs = _latest_runs(paths)
    store = PlanStore(paths)
    rows: list[PlanEvalRow] = []
    for task in tasks:
        try:
            plans = store.all(task.id)
        except ConfigError:
            continue
        for plan in plans:
            rows.append(_row(plan, runs.get(task.id)))
        shadow = store.shadow(task.id)
        if shadow is not None:
            rows.append(_row(shadow, runs.get(task.id)))
        for alternative in store.alternatives(task.id).values():
            rows.append(_row(alternative, runs.get(task.id)))
    by_mode: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = by_mode.setdefault(
            row.mode,
            {"plans": 0, "validated": 0, "approved": 0, "critic_allow": 0, "proved": 0},
        )
        bucket["plans"] += 1
        bucket["validated"] += int(bool(row.validation_ok))
        bucket["approved"] += int(row.approved)
        bucket["critic_allow"] += int(row.critic_allow is True)
        bucket["proved"] += int(row.run_state == "proved")
    scored = [row.critic_score for row in rows if row.critic_score is not None]
    return {
        "tasks": len(tasks),
        "plans": len(rows),
        "validated": sum(1 for row in rows if row.validation_ok),
        "approved": sum(1 for row in rows if row.approved),
        "critic_allow": sum(1 for row in rows if row.critic_allow is True),
        "avg_critic_score": (sum(scored) / len(scored)) if scored else None,
        "planner_tokens": sum(row.planner_tokens for row in rows),
        "planner_usd": sum(row.planner_usd for row in rows),
        "by_mode": by_mode,
        "rows": [row.model_dump(mode="json") for row in rows],
    }
