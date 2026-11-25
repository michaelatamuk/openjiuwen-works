"""Human approvals.

A plan gate is a state change bound to the drafted plan; it is not a chat reply. A decision is
approve, request changes or reject, it names who and which device, and an agent identity is refused.
"""

from __future__ import annotations

import contextlib
import os
from datetime import UTC, datetime, timedelta

from works.adapters.queue.store import Queue
from works.application.planning.memory import PlanMemory
from works.application.planning.service import PlanStore
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError, NotFoundError
from works.domain.records import Event, Task, TaskState

TTL_ENV = "WORKS_APPROVAL_TTL_HOURS"
QUORUM_ENV = "WORKS_REQUIRE_QUORUM"
DEFAULT_TTL_HOURS = 168
AGENT_ACTORS = frozenset({"agent", "harness", "model", "builder", "mira", "ai"})
DECISIONS = frozenset({"approved", "changes_requested", "rejected"})


def ttl_hours() -> int:
    raw = os.environ.get(TTL_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_TTL_HOURS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{TTL_ENV} must be a whole number of hours") from exc
    if value <= 0:
        raise ConfigError(f"{TTL_ENV} must be positive")
    return value


def quorum_required() -> bool:
    return os.environ.get(QUORUM_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def expires_at(now: datetime | None = None) -> str:
    moment = now or datetime.now(tz=UTC)
    return (moment + timedelta(hours=ttl_hours())).isoformat()


def approval_expired(event: Event | None, *, now: datetime | None = None) -> bool:
    if event is None:
        return True
    raw = str(event.data.get("expires_at") or "")
    if not raw:
        return False
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return True
    return moment <= (now or datetime.now(tz=UTC))


def _check_actor(by: str, actor_kind: str) -> str:
    actor = by.strip()
    if not actor:
        raise ConfigError("the plan gate needs a named person")
    if actor_kind != "person" or actor.lower() in AGENT_ACTORS:
        raise ConfigError("an agent cannot decide the plan gate; a person must approve it")
    return actor


check_actor = _check_actor


def decide_plan(
    paths: WorksPaths,
    task_id: str,
    *,
    decision: str = "approved",
    by: str = "person",
    device: str = "local",
    comment: str = "",
    actor_kind: str = "person",
    plan_id: str | None = None,
    plan_hash: str | None = None,
) -> tuple[Task, Event]:
    if decision not in DECISIONS:
        raise ConfigError(f"unknown gate decision {decision!r}")
    actor = _check_actor(by, actor_kind)
    queue = Queue(paths)
    task = queue.load(task_id)
    if task.state is not TaskState.PLANNING:
        raise ConfigError(f"task {task_id} is {task.state.value}; the plan gate needs planning")
    events = queue.events(task_id)
    plans = [event for event in events if event.type == "plan.drafted"]
    if not plans:
        raise ConfigError(f"task {task_id} has no drafted plan to decide")
    plan = plans[-1].data
    current_id = plan.get("plan_id")
    current_hash = plan.get("hash")
    if plan_id is not None and plan_id != current_id:
        raise ConfigError(f"the latest plan is {current_id or 'unversioned'}, not {plan_id}")
    if plan_hash is not None and plan_hash != current_hash:
        raise ConfigError("the plan hash does not match the latest plan; re-plan first")
    note = comment.strip()
    if decision in ("changes_requested", "rejected") and not note:
        raise ConfigError(f"{decision} needs a comment explaining what to change")
    if len(note) > 2000:
        raise ConfigError("the comment is too long")

    audit = {
        "gate": "plan",
        "decision": decision,
        "by": actor,
        "device": device.strip() or "local",
        "actor_kind": actor_kind,
        "comment": note,
        "commit": plan.get("base_commit"),
        "checks_sha": plan.get("checks_sha"),
        "plan_id": current_id,
        "plan_hash": current_hash,
        "plan_version": plan.get("version"),
    }

    if decision == "approved":
        prior = [
            event
            for event in events
            if event.type == "gate.approval"
            and event.data.get("plan_hash") == current_hash
            and event.data.get("decision") == "approved"
        ]
        if quorum_required():
            if any(
                event.data.get("by") == actor and event.data.get("device") == audit["device"]
                for event in prior
            ):
                raise ConfigError("the same person on the same device cannot satisfy a quorum")
            if not prior:
                pending = queue.append(
                    task_id,
                    "gate.approval",
                    {**audit, "expires_at": expires_at(), "note": "waiting for a second approver"},
                )
                return queue.load(task_id), pending
        if current_id and current_hash:
            with contextlib.suppress(NotFoundError):
                approved_plan = PlanStore(paths).approve(
                    task_id, plan_id=current_id, plan_hash=current_hash, by=actor
                )
                PlanMemory(paths).remember(approved_plan, by=actor)
        queue.transition(task_id, TaskState.PLAN_APPROVED)
        event = queue.append(
            task_id,
            "gate.decided",
            {**audit, "expires_at": expires_at(), "quorum": quorum_required()},
        )
        return queue.load(task_id), event

    if decision == "changes_requested":
        event = queue.append(task_id, "gate.decided", audit)
        return queue.load(task_id), event

    queue.transition(task_id, TaskState.BLOCKED)
    event = queue.append(task_id, "gate.decided", audit)
    return queue.load(task_id), event


def approve_plan(
    paths: WorksPaths,
    task_id: str,
    *,
    by: str = "cli",
    plan_id: str | None = None,
    plan_hash: str | None = None,
) -> tuple[Task, Event]:
    return decide_plan(
        paths,
        task_id,
        decision="approved",
        by=by,
        plan_id=plan_id,
        plan_hash=plan_hash,
    )
