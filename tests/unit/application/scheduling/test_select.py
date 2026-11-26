from __future__ import annotations

from datetime import UTC, datetime, timedelta

from works.application.scheduling.estimates import Estimate, group_key
from works.application.scheduling.policy import DispatchPolicy
from works.application.scheduling.select import (
    Signals,
    SkipReason,
    age_hours,
    evaluate,
    order_key,
    tick_plan,
)
from works.domain.enums import SourceKind, TaskState
from works.domain.task import Source, Task

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


def task(
    *,
    task_id: str = "t-1",
    flow: str = "fix-issue",
    labels: tuple[str, ...] = (),
    severity: str | None = None,
    kind: SourceKind = SourceKind.MANUAL,
    channel: str | None = None,
    state: TaskState = TaskState.QUEUED,
    created_at: datetime | None = None,
    attempts: int = 0,
    waiting_on: str | None = None,
    repo: str = "/repo",
) -> Task:
    return Task(
        id=task_id,
        flow=flow,
        product="P",
        repo=repo,
        source=Source(
            kind=kind,
            ref="R",
            title="t",
            labels=list(labels),
            severity=severity,
            channel=channel,
        ),
        state=state,
        created_at=created_at or NOW,
        updated_at=created_at or NOW,
        attempts=attempts,
        waiting_on=waiting_on,
    )


def policy(**overrides: object) -> DispatchPolicy:
    data: dict[str, object] = {"enabled": True, "allow": {"manual": True}}
    data.update(overrides)
    return DispatchPolicy.model_validate(data)


def signals(
    *,
    active_runs: int = 0,
    active_repos: frozenset[str] = frozenset(),
    remaining_usd: float | None = None,
    job_pool_pct: float = 0.0,
    api_p95_ms: float = 0.0,
    free_disk_gb: float = 999.0,
    provider_errors: int = 0,
    waiting_plans: int = 0,
    stale_approvals: frozenset[str] = frozenset(),
) -> Signals:
    return Signals(
        now=NOW,
        active_runs=active_runs,
        active_repos=active_repos,
        remaining_usd=remaining_usd,
        job_pool_pct=job_pool_pct,
        api_p95_ms=api_p95_ms,
        free_disk_gb=free_disk_gb,
        provider_errors=provider_errors,
        waiting_plans=waiting_plans,
        stale_approvals=stale_approvals,
    )


def test_a_manual_task_needs_manual_allowed() -> None:
    item = task()

    assert evaluate(item, policy(allow={"manual": False}), signals()) == (
        SkipReason.MANUAL_NOT_ALLOWED
    )
    assert evaluate(item, policy(), signals()) is None


def test_an_imported_task_needs_a_label() -> None:
    item = task(kind=SourceKind.TRACKER, channel="github")

    assert evaluate(item, policy(), signals()) == SkipReason.MISSING_LABEL
    labelled = task(kind=SourceKind.TRACKER, channel="github", labels=("works:auto",))
    assert evaluate(labelled, policy(), signals()) is None


def test_a_denied_label_wins_over_an_allow() -> None:
    item = task(kind=SourceKind.TRACKER, channel="github", labels=("works:auto", "works:hold"))

    assert evaluate(item, policy(), signals()) == SkipReason.DENIED_LABEL


def test_a_state_outside_the_level_is_not_runnable() -> None:
    proved = task(state=TaskState.PROVED)

    assert evaluate(proved, policy(), signals()) == SkipReason.NOT_RUNNABLE


def test_a_plan_approved_task_is_claimable_at_l2() -> None:
    approved = task(
        kind=SourceKind.TRACKER,
        channel="github",
        state=TaskState.PLAN_APPROVED,
        labels=("works:auto",),
    )
    body = policy(levels={"default": "L1", "by_source": {"github": "L2"}})

    assert evaluate(approved, body, signals()) is None


def test_stale_attempts_and_waits_are_refused() -> None:
    old = task(created_at=NOW - timedelta(hours=100))
    tried = task(attempts=2)
    waiting = task(waiting_on="review")

    assert evaluate(old, policy(), signals()) == SkipReason.STALE
    assert evaluate(tried, policy(), signals()) == SkipReason.ATTEMPTS_EXHAUSTED
    assert evaluate(waiting, policy(), signals()) == SkipReason.WAITING_ON_EVENT


def test_risk_above_the_level_cap_is_refused() -> None:
    critical = task(
        kind=SourceKind.TRACKER, channel="github", labels=("works:auto",), severity="S1"
    )
    body = policy(levels={"default": "L1", "by_source": {"github": "L2"}})

    assert evaluate(critical, body, signals()) == SkipReason.RISK_TOO_HIGH


def test_slots_budget_and_machine_refusals() -> None:
    item = task()

    assert evaluate(item, policy(), signals(active_repos=frozenset({"/repo"}))) == (
        SkipReason.REPO_BUSY
    )
    assert evaluate(item, policy(), signals(active_runs=2)) == SkipReason.GLOBAL_BUSY
    assert evaluate(item, policy(), signals(remaining_usd=0.0)) == SkipReason.BUDGET_EXHAUSTED
    assert evaluate(item, policy(), signals(job_pool_pct=90)) == SkipReason.SYSTEM_BUSY
    assert evaluate(item, policy(), signals(api_p95_ms=500)) == SkipReason.INTERACTIVE_LOAD
    assert evaluate(item, policy(), signals(free_disk_gb=1)) == SkipReason.LOW_DISK
    assert evaluate(item, policy(), signals(provider_errors=5)) == SkipReason.PROVIDER_DEGRADED
    assert evaluate(item, policy(), signals(waiting_plans=3)) == SkipReason.ATTENTION_FULL


def test_a_blackout_holds_the_tick() -> None:
    body = policy(windows={"blackout": ["11:00-13:00"]})

    assert evaluate(task(), body, signals()) == SkipReason.BLACKOUT


def test_per_run_cap_is_checked_against_the_estimate() -> None:
    body = policy(budget={"per_run_usd": 0.5})

    assert evaluate(task(), body, signals()) == SkipReason.RUN_BUDGET_CAP


def test_higher_risk_goes_first() -> None:
    low = task(task_id="t-low", severity="S4")
    critical = task(task_id="t-crit", severity="S1")
    plan = tick_plan([low, critical], policy(), signals())

    assert [item.task.id for item in plan.eligible] == ["t-crit", "t-low"]


def test_the_small_bucket_goes_first_between_equals() -> None:
    large = task(task_id="t-large", flow="fix-issue")
    small = task(task_id="t-small", flow="check-change")
    plan = tick_plan([large, small], policy(), signals())

    assert [item.task.id for item in plan.eligible] == ["t-small", "t-large"]


def test_budget_fragility_beats_size() -> None:
    large = task(task_id="t-large", flow="fix-issue")
    small = task(task_id="t-small", flow="check-change")
    plan = tick_plan([small, large], policy(), signals(remaining_usd=3.0))

    assert [item.task.id for item in plan.eligible] == ["t-large", "t-small"]


def test_starvation_forms_its_own_bucket() -> None:
    old_low = task(
        task_id="t-old",
        severity="S4",
        created_at=NOW - timedelta(hours=30),
    )
    fresh_medium = task(task_id="t-new", severity="S3")
    plan = tick_plan([fresh_medium, old_low], policy(), signals())

    assert [item.task.id for item in plan.eligible] == ["t-old", "t-new"]


def test_order_key_is_stable_for_equal_tasks() -> None:
    body = policy()
    one = task(task_id="t-a")
    two = task(task_id="t-b")
    plan = tick_plan([two, one], body, signals())

    keys = [order_key(candidate, body, signals()) for candidate in plan.eligible]
    assert keys[0][:5] == keys[1][:5]
    assert [item.task.id for item in plan.eligible] == ["t-a", "t-b"]


def test_age_is_never_negative() -> None:
    assert age_hours(task(created_at=NOW + timedelta(hours=2)), NOW) == 0.0


def test_a_stale_approval_is_refused() -> None:
    approved = task(
        kind=SourceKind.TRACKER,
        channel="github",
        labels=("works:auto",),
        state=TaskState.PLAN_APPROVED,
    )
    body = policy(levels={"default": "L2"})

    assert (
        evaluate(approved, body, signals(stale_approvals=frozenset({approved.id})))
        == SkipReason.STALE_APPROVAL
    )


def test_a_history_estimate_can_block_a_run() -> None:
    item = task()
    body = policy(estimates={"source": "history"}, budget={"per_run_usd": 5})
    history = {group_key("fix-issue", "medium"): Estimate(30, 60, 4.0, 6.0, 0.8, 10, "history")}

    assert evaluate(item, body, signals(), history) == SkipReason.RUN_BUDGET_CAP


def test_flow_product_and_repo_filters_are_typed() -> None:
    body = policy(allow={"manual": True, "flows": ["check-change"]})
    assert evaluate(task(), body, signals()) == SkipReason.FLOW_NOT_ALLOWED

    body = policy(allow={"manual": True, "products": ["Other"]})
    assert evaluate(task(), body, signals()) == SkipReason.NOT_ALLOWLISTED

    body = policy(allow={"manual": True, "repos": ["/elsewhere"]})
    assert evaluate(task(), body, signals()) == SkipReason.NOT_ALLOWLISTED


def test_a_plan_estimate_overrides_history_for_that_task() -> None:
    item = task()
    planned = Estimate(30, 45, 4.0, 6.0, 0.4, 0, "plan")

    assert (
        evaluate(
            item,
            policy(estimates={"source": "history"}, budget={"per_run_usd": 5}),
            signals(),
            None,
            {item.id: planned},
        )
        == SkipReason.RUN_BUDGET_CAP
    )
