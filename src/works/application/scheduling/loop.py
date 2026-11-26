"""The scheduler loop: one tick, typed decisions, no execution inside selection.

A tick claims at most the free slots and hands each claimed task to the caller. In the CLI that
caller runs the supervisor sequentially; in the daemon (next pass) it submits the existing run job.
"""

from __future__ import annotations

import json
import os
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from works.adapters.queue.atomic import atomic_write
from works.adapters.queue.store import Queue
from works.application import limits
from works.application.approvals.gates import approval_expired
from works.application.scheduling import lease
from works.application.scheduling.estimates import (
    Estimate,
    history_map,
    knn_estimate,
    titled_samples,
)
from works.application.scheduling.policy import DispatchPolicy, load_policy, risk_for_severity
from works.application.scheduling.select import Signals, TickPlan, tick_plan
from works.config.paths import WorksPaths
from works.domain.enums import TaskState
from works.domain.errors import WorksError
from works.domain.task import Task

STATE_FILE = "scheduler.json"


@dataclass
class TickResult:
    status: str
    claimed: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    reclaimed: list[str] = field(default_factory=list)
    order: list[str] = field(default_factory=list)
    executed: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None


TRANSIENT = frozenset({"harness_error", "internal_error", "timeout", "network_error"})


def terminal_failures(queue: Queue) -> frozenset[str]:
    failed: set[str] = set()
    if not queue.paths.queue.exists():
        return frozenset()
    for task in queue.list_tasks():
        events = queue.events(task.id)
        latest_failure = None
        latest_claim = None
        for event in events:
            if event.type == "scheduler.failed":
                latest_failure = event
            elif event.type == "scheduler.claimed":
                latest_claim = event
        if latest_failure is None:
            continue
        if latest_claim is not None and latest_claim.seq > latest_failure.seq:
            continue
        if latest_failure.data.get("retryable") is False:
            failed.add(task.id)
    return frozenset(failed)


def stale_approvals(paths: WorksPaths, now: datetime) -> frozenset[str]:
    """Plan/release approvals that expired; a hash mismatch is the next pass."""
    queue = Queue(paths)
    stale: set[str] = set()
    for task in queue.list_tasks():
        if task.state not in (TaskState.PLAN_APPROVED, TaskState.RELEASED):
            continue
        gate = "plan" if task.state is TaskState.PLAN_APPROVED else "release"
        events = queue.events(task.id)
        approved = [
            event
            for event in events
            if event.type == "gate.decided"
            and event.data.get("gate") == gate
            and event.data.get("decision") == "approved"
        ]
        if not approved:
            stale.add(task.id)
            continue
        latest = approved[-1]
        if approval_expired(latest, now=now):
            stale.add(task.id)
            continue
        if gate == "plan":
            drafted = [event for event in events if event.type == "plan.drafted"]
            if not drafted or drafted[-1].data.get("hash") != latest.data.get("plan_hash"):
                stale.add(task.id)
    return frozenset(stale)


def dispatcher_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


class Scheduler:
    def __init__(
        self,
        paths: WorksPaths,
        *,
        owner: str | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._paths = paths
        self._queue = Queue(paths)
        self._owner = owner or f"scheduler:{dispatcher_id()}"
        self._now = now or (lambda: datetime.now(tz=UTC))

    @property
    def paths(self) -> WorksPaths:
        return self._paths

    @property
    def owner(self) -> str:
        return self._owner

    @property
    def state_path(self) -> Path:
        return self._paths.state / STATE_FILE

    def _read_state(self) -> dict[str, object]:
        path = self.state_path
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write_state(self, state: dict[str, object]) -> None:
        self._paths.state.mkdir(parents=True, exist_ok=True)
        atomic_write(self.state_path, json.dumps(state, ensure_ascii=False, sort_keys=True))

    def paused(self) -> tuple[bool, str]:
        state = self._read_state()
        reason = str(state.get("pause_reason") or "")
        return bool(state.get("paused")), reason

    def pause(self, reason: str = "") -> None:
        state = self._read_state()
        state["paused"] = True
        state["pause_reason"] = reason
        state["paused_at"] = _iso(self._now())
        self._write_state(state)

    def resume(self) -> None:
        state = self._read_state()
        state["paused"] = False
        state["pause_reason"] = ""
        state["resumed_at"] = _iso(self._now())
        self._write_state(state)

    def _remaining_usd(self, policy: DispatchPolicy) -> float | None:
        cap = policy.budget.daily_usd if policy.budget.daily_usd is not None else limits.cap()
        if cap is None:
            return None
        return max(0.0, cap - limits.spent(self._paths))

    def signals(self, policy: DispatchPolicy, *, now: datetime | None = None) -> Signals:
        moment = now or self._now()
        active = lease.active_leases(self._paths, moment)
        tasks = self._queue.list_tasks()
        repos: frozenset[str] = frozenset()
        if active:
            by_id = {task.id: task for task in tasks}
            repos = frozenset(by_id[item.task_id].repo for item in active if item.task_id in by_id)
        waiting = sum(1 for task in tasks if task.state is TaskState.PLANNING)
        return Signals(
            now=moment,
            active_runs=len(active),
            active_repos=repos,
            remaining_usd=self._remaining_usd(policy),
            waiting_plans=waiting,
            stale_approvals=stale_approvals(self._paths, moment),
            terminal_failures=terminal_failures(self._queue),
        )

    def _history(self, policy: DispatchPolicy) -> dict[str, Estimate] | None:
        if policy.estimates.source != "history":
            return None
        return history_map(self._paths, min_samples=policy.estimates.min_samples)

    def plan(self, policy: DispatchPolicy | None = None) -> TickPlan:
        loaded = policy or load_policy(self._paths)
        return tick_plan(
            self._queue.list_tasks(),
            loaded,
            self.signals(loaded),
            self._history(loaded),
        )

    def status(self) -> dict[str, object]:
        policy = load_policy(self._paths)
        paused, reason = self.paused()
        state = self._read_state()
        planned = self.plan(policy)
        active = lease.active_leases(self._paths)
        return {
            "enabled": policy.enabled,
            "paused": paused or policy.paused,
            "pause_reason": reason,
            "tick_seconds": policy.tick_seconds,
            "levels": {
                "default": policy.levels.default,
                "by_source": policy.levels.by_source,
            },
            "limits": {
                "global": policy.concurrency.global_slots,
                "per_repo": policy.concurrency.per_repo,
                "per_run_usd": policy.budget.per_run_usd,
                "remaining_usd": self._remaining_usd(policy),
            },
            "active": [
                {
                    "task_id": item.task_id,
                    "owner": item.owner,
                    "expires_at": item.expires_at.isoformat(),
                }
                for item in active
            ],
            "eligible": [item.task.id for item in planned.eligible],
            "waiting": {task_id: reason.value for task_id, reason in planned.skipped.items()},
            "last_tick": state.get("last_tick"),
            "counters": state.get("counters", {}),
            "owner": self._owner,
        }

    def _shadow(
        self,
        planned: TickPlan,
        tasks: list[Task],
        policy: DispatchPolicy,
        moment: datetime,
    ) -> None:
        titles = {task.id: task.source.title for task in tasks}
        samples = titled_samples(self._paths)
        rule = [item.task.id for item in planned.eligible]
        scored: list[tuple[int, int, float, str]] = []
        for candidate in planned.eligible:
            title = titles.get(candidate.task.id, "")
            risk = risk_for_severity(candidate.task.source.severity)
            estimate = knn_estimate(
                samples,
                title=title,
                flow=candidate.task.flow,
                risk=risk,
                min_samples=3,
            )
            minutes = estimate.p50_min if estimate is not None else candidate.estimate.p50_min
            starving = 0 if candidate.age_hours >= policy.queue.starvation_boost_hours else 1
            scored.append((starving, -candidate.risk_rank, minutes, candidate.task.id))
        would = [item[3] for item in sorted(scored)]
        if would == rule:
            return
        self._queue.append(
            planned.eligible[0].task.id,
            "scheduler.shadow",
            {"rule": rule, "would": would, "at": _iso(moment)},
        )

    def tick(
        self,
        *,
        execute: Callable[[str], None] | None = None,
        limit: int | None = None,
        hold: bool = False,
        now: datetime | None = None,
    ) -> TickResult:
        policy = load_policy(self._paths)
        if not policy.enabled:
            return TickResult(status="disabled")
        paused, _reason = self.paused()
        if paused or policy.paused:
            return TickResult(status="paused")
        moment = now or self._now()
        with lease.dispatcher(self._paths) as held:
            if not held:
                return TickResult(status="busy")
            atomic_write(
                self._paths.state / "dispatcher.json",
                json.dumps({"owner": self._owner, "at": _iso(moment)}, sort_keys=True),
            )
            reclaimed = lease.reclaim_stale(self._paths, self._queue, moment)
            tasks = self._queue.list_tasks()
            planned = tick_plan(
                tasks,
                policy,
                self.signals(policy, now=moment),
                self._history(policy),
            )
            if policy.order.mode == "shadow" and len(planned.eligible) >= 2:
                self._shadow(planned, tasks, policy, moment)
            active = lease.active_leases(self._paths, moment)
            free = max(0, policy.concurrency.global_slots - len(active))
            if limit is not None:
                free = min(free, max(0, limit))
            result = TickResult(
                status="ok",
                skipped={task_id: reason.value for task_id, reason in planned.skipped.items()},
                reclaimed=reclaimed,
                order=[item.task.id for item in planned.eligible],
            )
            for candidate in planned.eligible[:free]:
                ttl = int(max(600.0, candidate.estimate.p90_min * 90.0))
                try:
                    lease.claim(
                        self._paths,
                        candidate.task.id,
                        owner=self._owner,
                        ttl_seconds=ttl,
                        estimated_min=candidate.estimate.p50_min,
                        now=moment,
                    )
                except WorksError as exc:
                    result.skipped[candidate.task.id] = type(exc).__name__
                    continue
                self._queue.append(
                    candidate.task.id,
                    "scheduler.claimed",
                    {
                        "owner": self._owner,
                        "level": candidate.level,
                        "trigger": "scheduler",
                        "attempt": candidate.task.attempts + 1,
                        "estimate": {
                            "p50_min": candidate.estimate.p50_min,
                            "p90_min": candidate.estimate.p90_min,
                            "p90_usd": candidate.estimate.p90_usd,
                            "source": candidate.estimate.source,
                        },
                        "age_hours": round(candidate.age_hours, 2),
                    },
                )
                result.claimed.append(candidate.task.id)
                if execute is None:
                    if not hold:
                        lease.release(self._paths, candidate.task.id, owner=self._owner)
                    continue
                try:
                    execute(candidate.task.id)
                    result.executed.append({"task_id": candidate.task.id, "result": "ok"})
                except Exception as exc:
                    code = str(getattr(exc, "code", "internal_error"))
                    self._queue.append(
                        candidate.task.id,
                        "scheduler.failed",
                        {"code": code, "error": str(exc), "retryable": code in TRANSIENT},
                    )
                    result.executed.append(
                        {"task_id": candidate.task.id, "result": f"{code}: {exc}"}
                    )
                finally:
                    lease.release(self._paths, candidate.task.id, owner=self._owner)
            state = self._read_state()
            previous = state.get("last_reasons")
            last: dict[str, str] = (
                {str(key): str(value) for key, value in previous.items()}
                if isinstance(previous, dict)
                else {}
            )
            for task_id, reason in result.skipped.items():
                if last.get(task_id) != reason and self._queue.exists(task_id):
                    self._queue.append(
                        task_id,
                        "scheduler.skipped",
                        {"reason": reason, "owner": self._owner},
                    )
            state["last_reasons"] = dict(result.skipped)
            state["last_tick"] = _iso(moment)
            counters = state.get("counters")
            counts: dict[str, int] = (
                {str(key): int(value) for key, value in counters.items()}
                if isinstance(counters, dict)
                else {}
            )
            for reason in result.skipped.values():
                counts[reason] = counts.get(reason, 0) + 1
            state["counters"] = counts
            self._write_state(state)
            return result
