"""Selection and admission: pure functions, typed reasons, deterministic order.

The scheduler decides *whether* a task may run and *whether it should run now*. Execution is not in
this module; a caller claims and then runs (or submits) the selected task.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from works.application.scheduling.estimates import Estimate, group_key
from works.application.scheduling.policy import (
    DispatchPolicy,
    Level,
    in_blackout,
    level_for,
    risk_for_severity,
    risk_rank,
)
from works.domain.enums import SourceKind, TaskState
from works.domain.task import Task

LEVEL_STATES: dict[Level, frozenset[TaskState]] = {
    "L1": frozenset({TaskState.QUEUED}),
    "L2": frozenset({TaskState.QUEUED, TaskState.PLAN_APPROVED}),
    "L3": frozenset({TaskState.QUEUED, TaskState.PLAN_APPROVED, TaskState.RELEASED}),
}


class SkipReason(StrEnum):
    DISABLED = "disabled"
    PAUSED = "paused"
    NOT_RUNNABLE = "not_runnable"
    NOT_ALLOWLISTED = "not_allowlisted"
    MISSING_LABEL = "missing_label"
    DENIED_LABEL = "denied_label"
    MANUAL_NOT_ALLOWED = "manual_not_allowed"
    FLOW_NOT_ALLOWED = "flow_not_allowed"
    STALE = "stale"
    WAITING_ON_EVENT = "waiting_on_event"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    BACKOFF = "backoff"
    RISK_TOO_HIGH = "risk_too_high"
    STALE_APPROVAL = "stale_approval"
    TERMINAL_FAILURE = "terminal_failure"
    REPO_BUSY = "repo_busy"
    GLOBAL_BUSY = "global_busy"
    BUDGET_EXHAUSTED = "budget_exhausted"
    RUN_BUDGET_CAP = "run_budget_cap"
    SYSTEM_BUSY = "system_busy"
    INTERACTIVE_LOAD = "interactive_load"
    LOW_DISK = "low_disk"
    PROVIDER_DEGRADED = "provider_degraded"
    ATTENTION_FULL = "attention_full"
    BLACKOUT = "blackout"


_STATIC: dict[str, Estimate] = {
    "fix-issue": Estimate(20.0, 45.0, 1.0, 2.5, 0.1, 0, "static"),
    "check-change": Estimate(10.0, 25.0, 0.5, 1.2, 0.1, 0, "static"),
}
_DEFAULT_ESTIMATE = Estimate(20.0, 45.0, 1.0, 2.5, 0.1, 0, "static")


def estimate_for(
    task: Task,
    policy: DispatchPolicy,
    history: dict[str, Estimate] | None = None,
) -> Estimate:
    """History when the policy asks for it and has enough samples; a static prior otherwise."""
    if history is not None and policy.estimates.source == "history":
        risk = risk_for_severity(task.source.severity)
        found = history.get(group_key(task.flow, risk))
        if found is not None:
            return found
    return _STATIC.get(task.flow, _DEFAULT_ESTIMATE)


@dataclass(frozen=True)
class Signals:
    now: datetime
    active_runs: int = 0
    active_repos: frozenset[str] = frozenset()
    remaining_usd: float | None = None
    job_pool_pct: float = 0.0
    api_p95_ms: float = 0.0
    free_disk_gb: float = 999.0
    provider_errors: int = 0
    waiting_plans: int = 0
    stale_approvals: frozenset[str] = frozenset()
    terminal_failures: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Candidate:
    task: Task
    estimate: Estimate
    age_hours: float
    level: Level
    risk_rank: int


@dataclass(frozen=True)
class TickPlan:
    eligible: list[Candidate] = field(default_factory=list)
    skipped: dict[str, SkipReason] = field(default_factory=dict)


def source_name(task: Task) -> str:
    channel = (task.source.channel or "").strip().lower()
    if channel:
        return channel
    return task.source.kind.value


def age_hours(task: Task, now: datetime) -> float:
    created = (
        task.created_at
        if task.created_at.tzinfo is not None
        else (task.created_at.replace(tzinfo=now.tzinfo))
    )
    return max(0.0, (now - created).total_seconds() / 3600.0)


def task_risk(task: Task) -> int:
    return risk_rank(risk_for_severity(task.source.severity))


def _policy_reason(task: Task, policy: DispatchPolicy, source: str) -> SkipReason | None:
    allow = policy.allow
    if task.source.kind is SourceKind.MANUAL:
        if not allow.manual:
            return SkipReason.MANUAL_NOT_ALLOWED
        return None
    if allow.sources and source not in allow.sources:
        return SkipReason.NOT_ALLOWLISTED
    if allow.labels and not set(allow.labels) & set(task.source.labels):
        return SkipReason.MISSING_LABEL
    return None


def _denied(task: Task, policy: DispatchPolicy) -> bool:
    return bool(set(policy.allow.labels_deny) & set(task.source.labels))


def evaluate(
    task: Task,
    policy: DispatchPolicy,
    signals: Signals,
    history: dict[str, Estimate] | None = None,
) -> SkipReason | None:
    source = source_name(task)
    level = level_for(policy, source)
    estimate = estimate_for(task, policy, history)

    if task.state not in LEVEL_STATES[level]:
        return SkipReason.NOT_RUNNABLE
    if task.id in signals.stale_approvals:
        return SkipReason.STALE_APPROVAL
    if task.id in signals.terminal_failures:
        return SkipReason.TERMINAL_FAILURE
    if task.waiting_on is not None:
        return SkipReason.WAITING_ON_EVENT
    age = age_hours(task, signals.now)
    if age > policy.queue.max_age_hours:
        return SkipReason.STALE
    if task.attempts >= policy.queue.max_attempts:
        return SkipReason.ATTEMPTS_EXHAUSTED
    if task.attempts > 0 and age > 0:
        updated = (
            task.updated_at
            if task.updated_at.tzinfo is not None
            else (task.updated_at.replace(tzinfo=signals.now.tzinfo))
        )
        since_s = (signals.now - updated).total_seconds()
        if since_s < policy.queue.backoff_seconds:
            return SkipReason.BACKOFF

    if _denied(task, policy):
        return SkipReason.DENIED_LABEL
    policy_reason = _policy_reason(task, policy, source)
    if policy_reason is not None:
        return policy_reason
    if policy.allow.flows and task.flow not in policy.allow.flows:
        return SkipReason.FLOW_NOT_ALLOWED
    if policy.allow.products and task.product not in policy.allow.products:
        return SkipReason.NOT_ALLOWLISTED
    if policy.allow.repos and task.repo not in policy.allow.repos:
        return SkipReason.NOT_ALLOWLISTED

    risk = task_risk(task)
    cap = None
    if level == "L2":
        cap = risk_rank(policy.allow.risk_max_for_L2)
    elif level == "L3":
        cap = risk_rank(policy.allow.risk_max_for_L3)
    if cap is not None and risk > cap:
        return SkipReason.RISK_TOO_HIGH

    if task.repo in signals.active_repos:
        return SkipReason.REPO_BUSY
    if signals.active_runs >= policy.concurrency.global_slots:
        return SkipReason.GLOBAL_BUSY

    if signals.remaining_usd is not None:
        if signals.remaining_usd <= 0:
            return SkipReason.BUDGET_EXHAUSTED
        if estimate.p90_usd > signals.remaining_usd:
            return SkipReason.BUDGET_EXHAUSTED
    if estimate.p90_usd > policy.budget.per_run_usd:
        return SkipReason.RUN_BUDGET_CAP

    if signals.job_pool_pct >= policy.resources.pause_when_job_pool_pct:
        return SkipReason.SYSTEM_BUSY
    if signals.api_p95_ms >= policy.resources.pause_when_api_p95_ms:
        return SkipReason.INTERACTIVE_LOAD
    if signals.free_disk_gb < policy.resources.min_free_disk_gb:
        return SkipReason.LOW_DISK
    if signals.provider_errors >= policy.resources.pause_on_provider_errors:
        return SkipReason.PROVIDER_DEGRADED
    if signals.waiting_plans >= policy.attention.max_waiting_plans:
        return SkipReason.ATTENTION_FULL
    if in_blackout(policy, signals.now):
        return SkipReason.BLACKOUT
    return None


def _bucket(estimate: Estimate, policy: DispatchPolicy) -> int:
    if estimate.p50_min <= policy.priority.size_buckets.small_max_minutes:
        return 0
    if estimate.p50_min >= policy.priority.size_buckets.large_min_minutes:
        return 2
    return 1


def order_key(
    candidate: Candidate,
    policy: DispatchPolicy,
    signals: Signals,
) -> tuple[int, int, int, int, float, str]:
    """starvation, risk, budget fragility, size bucket, age."""
    starving = 0 if candidate.age_hours >= policy.queue.starvation_boost_hours else 1
    fragile = 0
    if (
        signals.remaining_usd is not None
        and signals.remaining_usd > 0
        and candidate.estimate.p90_usd > signals.remaining_usd / 2
    ):
        fragile = 1
    return (
        starving,
        -candidate.risk_rank,
        -fragile,
        _bucket(candidate.estimate, policy),
        -candidate.age_hours,
        candidate.task.id,
    )


def tick_plan(
    tasks: list[Task],
    policy: DispatchPolicy,
    signals: Signals,
    history: dict[str, Estimate] | None = None,
) -> TickPlan:
    eligible: list[Candidate] = []
    skipped: dict[str, SkipReason] = {}
    for task in tasks:
        reason = evaluate(task, policy, signals, history)
        if reason is not None:
            skipped[task.id] = reason
            continue
        source = source_name(task)
        eligible.append(
            Candidate(
                task=task,
                estimate=estimate_for(task, policy, history),
                age_hours=age_hours(task, signals.now),
                level=level_for(policy, source),
                risk_rank=task_risk(task),
            )
        )
    eligible.sort(key=lambda item: order_key(item, policy, signals))
    return TickPlan(eligible=eligible, skipped=skipped)
