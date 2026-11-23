"""Human approvals.

A plan gate is a state change bound to the drafted plan; it is not a chat reply.
"""

from __future__ import annotations

import contextlib

from .config import WorksPaths
from .errors import ConfigError, NotFoundError
from .planner import PlanStore
from .queue import Queue
from .records import Event, Task, TaskState


def approve_plan(
    paths: WorksPaths,
    task_id: str,
    *,
    by: str = "cli",
    plan_id: str | None = None,
    plan_hash: str | None = None,
) -> tuple[Task, Event]:
    queue = Queue(paths)
    task = queue.load(task_id)
    if task.state is not TaskState.PLANNING:
        raise ConfigError(f"task {task_id} is {task.state.value}; the plan gate needs planning")
    plans = [event for event in queue.events(task_id) if event.type == "plan.drafted"]
    if not plans:
        raise ConfigError(f"task {task_id} has no drafted plan to approve")
    plan = plans[-1].data
    current_id = plan.get("plan_id")
    current_hash = plan.get("hash")
    if plan_id is not None and plan_id != current_id:
        raise ConfigError(
            f"the latest plan is {current_id or 'unversioned'}, not {plan_id}; re-plan first"
        )
    if plan_hash is not None and plan_hash != current_hash:
        raise ConfigError("the plan hash does not match the latest plan; re-plan first")
    if current_id and current_hash:
        # Legacy tasks predate versioned plan artefacts; the event remains the record.
        with contextlib.suppress(NotFoundError):
            PlanStore(paths).approve(task_id, plan_id=current_id, plan_hash=current_hash, by=by)
    queue.transition(task_id, TaskState.PLAN_APPROVED)
    event = queue.append(
        task_id,
        "gate.decided",
        {
            "gate": "plan",
            "decision": "approved",
            "by": by,
            "commit": plan.get("base_commit"),
            "checks_sha": plan.get("checks_sha"),
            "plan_id": current_id,
            "plan_hash": current_hash,
            "plan_version": plan.get("version"),
        },
    )
    return queue.load(task_id), event
