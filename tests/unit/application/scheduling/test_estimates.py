from __future__ import annotations

from works.application.scheduling.estimates import (
    Sample,
    backtest,
    estimate_from,
    estimate_from_plan,
    group_estimates,
    knn_estimate,
    plan_map,
    quantile,
    read_samples,
    titled_samples,
)


def sample(
    minutes: float,
    *,
    flow: str = "fix-issue",
    risk: str = "medium",
    usd: float = 1.0,
) -> Sample:
    return Sample(flow=flow, risk=risk, minutes=minutes, usd=usd)


def test_quantile_interpolates() -> None:
    assert quantile([1, 2, 3, 4], 0.5) == 2.5
    assert quantile([10], 0.9) == 10
    assert quantile([], 0.5) == 0.0


def test_estimate_carries_samples_and_confidence() -> None:
    estimate = estimate_from([sample(10), sample(20), sample(30)])

    assert estimate.p50_min == 20
    assert estimate.p90_min >= 20
    assert estimate.samples == 3
    assert estimate.confidence == 3 / 20
    assert estimate.source == "history"


def test_history_needs_a_minimum_sample_count() -> None:
    samples = [sample(10) for _ in range(4)]

    assert group_estimates(samples, min_samples=5) == {}
    assert "fix-issue|medium" in group_estimates(samples, min_samples=4)


def test_backtest_coverage_and_loss() -> None:
    report = backtest([sample(10) for _ in range(8)], min_samples=5)

    assert report["samples"] == 8
    assert report["coverage_p90"] == 1.0
    assert report["pinball"] == 0.0


def test_backtest_is_empty_without_enough_history() -> None:
    report = backtest([sample(10)], min_samples=5)

    assert report["samples"] == 0
    assert report["coverage_p90"] == 0.0


def test_plan_estimates_fill_a_thin_history() -> None:
    samples = [
        Sample(flow="fix-issue", risk="medium", minutes=30, usd=2, plan_minutes=12, plan_usd=0.8)
        for _ in range(2)
    ]

    plan = plan_map(samples)

    assert plan["fix-issue|medium"].source == "plan"
    assert plan["fix-issue|medium"].p50_min == 12


def test_evidence_files_become_samples(paths) -> None:
    run_dir = paths.runs / "r-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": "r-1",
        "task_id": "t-x",
        "flow": "fix-issue",
        "product": "P",
        "source": "manual:R",
        "state": "proved",
        "stop_reason": "completed",
        "duration_ms": 600_000,
        "usd": 1.5,
        "plan_estimated_minutes": 12,
        "plan_estimated_usd": 0.8,
    }
    (run_dir / "evidence.json").write_text(__import__("json").dumps(payload), encoding="utf-8")

    samples = read_samples(paths)
    assert samples[0].minutes == 10
    assert samples[0].plan_minutes == 12
    assert titled_samples(paths)[0].task_id == "t-x"


def test_invalid_evidence_is_skipped(paths) -> None:
    run_dir = paths.runs / "r-bad"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "evidence.json").write_text("{not json", encoding="utf-8")

    assert read_samples(paths) == []


def test_similarity_and_knn_need_content() -> None:
    from works.application.scheduling.estimates import knn_estimate, similarity

    assert similarity("", "anything") == 0.0
    assert knn_estimate([], title="x", flow="fix-issue", risk="medium") is None
    assert (
        knn_estimate(
            [sample(10, flow="check-change", risk="low")],
            title="nothing alike",
            flow="fix-issue",
            risk="medium",
        )
        is None
    )


def test_plan_estimates_are_widened_for_the_tail() -> None:
    estimate = estimate_from_plan(30, 2.0)

    assert estimate is not None
    assert estimate.source == "plan"
    assert estimate.p50_min == 30
    assert estimate.p90_min == 45


def test_similar_tasks_use_labels_and_paths() -> None:
    samples = [
        Sample(
            flow="fix-issue",
            risk="medium",
            minutes=8,
            usd=1,
            title="export drops the last column",
            labels=frozenset({"ui"}),
            paths=frozenset({"web/export.py"}),
            source="github",
        )
        for _ in range(4)
    ]

    estimate = knn_estimate(
        samples,
        title="export drops a column",
        flow="fix-issue",
        risk="medium",
        labels=frozenset({"ui"}),
        paths=frozenset({"web/export.py"}),
        source="github",
        min_samples=3,
    )

    assert estimate is not None
    assert estimate.source == "knn"
    assert estimate.p50_min == 8
    assert estimate.samples == 4


def test_backtest_reports_groups_and_tail_misses() -> None:
    report = backtest([sample(10) for _ in range(8)], min_samples=5)

    assert report["tail_misses"] == 0
    groups = report["groups"]
    assert isinstance(groups, list) and groups
    assert groups[0]["group"] == "fix-issue|medium"
