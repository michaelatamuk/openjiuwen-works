"""Human approvals.

A plan gate is a state change bound to the drafted plan; it is not a chat reply.
"""

from __future__ import annotations

from .config import WorksPaths
from .errors import ConfigError
from .queue import Queue
from .records import Event, Task, TaskState


def approve_plan(paths: WorksPaths, task_id: str, *, by: str = "cli") -> tuple[Task, Event]:
    queue = Queue(paths)
    task = queue.load(task_id)
    if task.state is not TaskState.PLANNING:
        raise ConfigError(f"task {task_id} is {task.state.value}; the plan gate needs planning")
    plans = [event for event in queue.events(task_id) if event.type == "plan.drafted"]
    if not plans:
        raise ConfigError(f"task {task_id} has no drafted plan to approve")
    plan = plans[-1].data
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
        },
    )
    return queue.load(task_id), event
