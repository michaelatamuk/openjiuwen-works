from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from works.adapters.queue.store import Queue
from works.application.scheduling.promotion import (
    promote,
    promotion_ok,
    readiness,
    shadow_stats,
)
from works.domain.errors import ConfigError
from works.domain.records import Source, SourceKind


def _task(paths) -> str:
    task, _created = Queue(paths).submit(
        source=Source(kind=SourceKind.MANUAL, ref="R", title="t"),
        flow="fix-issue",
        product="P",
        repo=str(paths.root / "repo"),
    )
    return task.id


def _shadow(paths, *, count: int = 50, agree: int = 45, weeks: float = 5.0) -> None:
    task_id = _task(paths)
    queue = Queue(paths)
    start = datetime.now(tz=UTC) - timedelta(weeks=weeks)
    for index in range(count):
        queue.append(
            task_id,
            "scheduler.shadow",
            {
                "rule": ["a"],
                "would": ["a"] if index < agree else ["b"],
            },
            ts=start + timedelta(weeks=weeks) * (index / max(count - 1, 1)),
        )


def test_shadow_stats_count_agreement_and_weeks(paths) -> None:
    _shadow(paths)

    stats = shadow_stats(paths)

    assert stats["shadow_claims"] == 50
    assert abs(float(stats["agreement"]) - 0.9) < 0.001
    assert float(stats["weeks"]) >= 4.5


def test_readiness_requires_every_check(paths, monkeypatch) -> None:
    monkeypatch.setattr(
        "works.application.scheduling.promotion.backtest",
        lambda *_: {"coverage_p90": 0.9},
    )
    _shadow(paths)

    report = readiness(paths)

    assert report["ready"] is True
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert all(checks.values())


def test_promotion_writes_a_record_after_evidence(paths, monkeypatch) -> None:
    monkeypatch.setattr(
        "works.application.scheduling.promotion.backtest",
        lambda *_: {"coverage_p90": 0.9},
    )
    _shadow(paths)

    record = promote(paths, by="anna", device="laptop")

    assert record["by"] == "anna"
    assert record["device"] == "laptop"
    assert promotion_ok(paths) is True


def test_promotion_needs_evidence(paths) -> None:
    with pytest.raises(ConfigError, match="not ready"):
        promote(paths, by="anna")


def test_an_agent_cannot_promote(paths) -> None:
    with pytest.raises(ConfigError, match="person"):
        promote(paths, by="builder")
