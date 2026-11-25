from __future__ import annotations

from works.application.scheduling.estimates import (
    Sample,
    backtest,
    estimate_from,
    group_estimates,
    quantile,
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
