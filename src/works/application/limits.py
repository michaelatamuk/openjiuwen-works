"""The daily spend ceiling, separate from the per-run budget on the task.

The per-run budget answers "may this run continue?". The daily ceiling answers "may Works spend
more money today?". Both fail with a typed `budget_exceeded`, never a silent stop.

The number comes from the append-only ledger (`<home>/ledger.jsonl`), so there is one source of
truth and no second file to keep in sync.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from works.adapters.queue.ledger import Ledger
from works.config.paths import WorksPaths
from works.domain.errors import BudgetError, ConfigError

ENV = "WORKS_DAILY_USD"


def cap() -> float | None:
    """The ceiling in USD, or None when the operator did not set one."""
    raw = os.environ.get(ENV)
    if raw is None or not raw.strip():
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{ENV} must be a number, got {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"{ENV} must be greater than zero, got {value}")
    return value


def _day(value: str | None) -> str:
    return value or datetime.now(tz=UTC).date().isoformat()


def spent(paths: WorksPaths, day: str | None = None) -> float:
    target = _day(day)
    total = 0.0
    for row in Ledger(paths.ledger).rows():
        stamp = row.ts if row.ts.tzinfo is not None else row.ts.replace(tzinfo=UTC)
        if stamp.astimezone(UTC).date().isoformat() == target:
            total += float(row.usd or 0.0)
    return total


def check(paths: WorksPaths, *, add_usd: float = 0.0) -> None:
    """Raise before the next model call when today's spend would pass the ceiling."""
    limit = cap()
    if limit is None:
        return
    projected = spent(paths) + max(add_usd, 0.0)
    if projected > limit:
        raise BudgetError(
            f"daily spend would reach ${projected:.2f}, above {ENV}=${limit:.2f}; "
            "raise the ceiling or wait for the next UTC day"
        )
