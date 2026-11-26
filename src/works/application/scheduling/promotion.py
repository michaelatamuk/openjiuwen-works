"""Promotion of a learned order: evidence first, a person second, a record last."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from works.adapters.queue.atomic import atomic_write
from works.adapters.queue.store import Queue
from works.application.approvals.gates import check_actor
from works.application.scheduling.estimates import backtest, enriched_samples
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError
from works.domain.records import Event

PROMOTION_FILE = "order-promotion.json"
REQUIRED_CLAIMS = 50
REQUIRED_WEEKS = 4.0
COVERAGE_BAND = (0.85, 0.95)
MIN_AGREEMENT = 0.8


def _path(paths: WorksPaths) -> Path:
    return paths.state / PROMOTION_FILE


def _parse(moment: str) -> datetime | None:
    try:
        value = datetime.fromisoformat(moment)
    except ValueError:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def shadow_stats(paths: WorksPaths) -> dict[str, object]:
    queue = Queue(paths)
    events: list[Event] = []
    if queue.paths.queue.exists():
        for task in queue.list_tasks():
            events.extend(
                event for event in queue.events(task.id) if event.type == "scheduler.shadow"
            )
    if not events:
        return {
            "shadow_claims": 0,
            "agreement": 0.0,
            "weeks": 0.0,
            "first": None,
            "last": None,
        }
    agreements = sum(1 for event in events if event.data.get("rule") == event.data.get("would"))
    first = min(event.ts for event in events)
    last = max(event.ts for event in events)
    return {
        "shadow_claims": len(events),
        "agreement": agreements / len(events),
        "weeks": max(0.0, (last - first).total_seconds() / (7 * 24 * 3600)),
        "first": first.isoformat(),
        "last": last.isoformat(),
    }


def readiness(paths: WorksPaths) -> dict[str, object]:
    stats = shadow_stats(paths)
    coverage = cast(float, backtest(enriched_samples(paths))["coverage_p90"])
    claims = cast(int, stats["shadow_claims"])
    weeks = cast(float, stats["weeks"])
    agreement = cast(float, stats["agreement"])
    checks = {
        f"shadow claims >= {REQUIRED_CLAIMS}": claims >= REQUIRED_CLAIMS,
        f"weeks >= {REQUIRED_WEEKS:.0f}": weeks >= REQUIRED_WEEKS,
        f"agreement >= {MIN_AGREEMENT:.0%}": agreement >= MIN_AGREEMENT,
        f"p90 coverage in {COVERAGE_BAND[0]:.0%}..{COVERAGE_BAND[1]:.0%}": (
            COVERAGE_BAND[0] <= coverage <= COVERAGE_BAND[1]
        ),
    }
    return {
        "shadow_claims": claims,
        "weeks": weeks,
        "agreement": agreement,
        "coverage": coverage,
        "checks": checks,
        "ready": all(checks.values()),
    }


def promotion_ok(paths: WorksPaths) -> bool:
    path = _path(paths)
    if not path.exists():
        return False
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(record, dict) or record.get("approved") is not True:
        return False
    try:
        claims = int(record["shadow_claims"])
        weeks = float(record["weeks"])
        coverage = float(record["coverage"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        claims >= REQUIRED_CLAIMS
        and weeks >= REQUIRED_WEEKS
        and COVERAGE_BAND[0] <= coverage <= COVERAGE_BAND[1]
    )


def promote(paths: WorksPaths, *, by: str, device: str = "local") -> dict[str, object]:
    actor = check_actor(by, "person")
    report = readiness(paths)
    if not report["ready"]:
        checks = cast(dict[str, bool], report["checks"])
        failed = [name for name, passed in checks.items() if not passed]
        raise ConfigError("a learned order is not ready: " + "; ".join(failed))
    record: dict[str, object] = {
        "approved": True,
        "by": actor,
        "device": device.strip() or "local",
        "at": datetime.now(tz=UTC).isoformat(),
        "shadow_claims": report["shadow_claims"],
        "weeks": report["weeks"],
        "coverage": report["coverage"],
        "agreement": report["agreement"],
    }
    paths.state.mkdir(parents=True, exist_ok=True)
    atomic_write(_path(paths), json.dumps(record, ensure_ascii=False, sort_keys=True))
    return record
