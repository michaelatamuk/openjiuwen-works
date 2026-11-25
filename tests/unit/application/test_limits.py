from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from works.adapters.queue.ledger import Ledger
from works.application import limits
from works.domain.errors import BudgetError, ConfigError
from works.domain.ledger import LedgerRow
from works.domain.records import TaskState


def _row(paths, *, usd: float, ts: datetime | None = None) -> None:
    Ledger(paths.ledger).append(
        LedgerRow(
            task_id="t-1",
            run_id="r-1",
            state=TaskState.PROVED,
            tokens=100,
            usd=usd,
            **({"ts": ts} if ts is not None else {}),
        )
    )


def test_no_ceiling_means_no_check(paths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(limits.ENV, raising=False)
    _row(paths, usd=999.0)

    assert limits.cap() is None
    limits.check(paths, add_usd=999.0)


def test_an_invalid_ceiling_is_a_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(limits.ENV, "a lot")
    with pytest.raises(ConfigError, match="must be a number"):
        limits.cap()

    monkeypatch.setenv(limits.ENV, "0")
    with pytest.raises(ConfigError, match="greater than zero"):
        limits.cap()


def test_spend_is_summed_for_today_only(paths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(limits.ENV, "10")
    now = datetime.now(tz=UTC)
    _row(paths, usd=2.5)
    _row(paths, usd=3.0)
    _row(paths, usd=100.0, ts=now - timedelta(days=1))

    assert limits.spent(paths) == pytest.approx(5.5)


def test_the_ceiling_counts_the_call_about_to_happen(
    paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(limits.ENV, "5")
    _row(paths, usd=3.0)

    limits.check(paths, add_usd=1.5)
    with pytest.raises(BudgetError, match="daily spend"):
        limits.check(paths, add_usd=2.5)


def test_a_malformed_ledger_row_is_not_silently_ignored(
    paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(limits.ENV, "5")
    paths.ledger.write_text("{not json}\n", encoding="utf-8")

    with pytest.raises(Exception, match="not a valid ledger row"):
        limits.spent(paths)
