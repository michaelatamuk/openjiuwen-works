"""Estimates from stored evidence: p50/p90, confidence, never a promise.

The scheduler needs to know whether a run fits a budget or a window, and which of two equal-risk
tasks is shorter. It does not need a deadline. This module reads `runs/*/evidence.json`, groups by
`flow` and `risk`, and returns empirical quantiles once a group has enough samples.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from works.adapters.queue.store import Queue
from works.config.paths import WorksPaths
from works.domain.evidence.models import Evidence


@dataclass(frozen=True)
class Estimate:
    p50_min: float
    p90_min: float
    p50_usd: float
    p90_usd: float
    confidence: float
    samples: int
    source: str


@dataclass(frozen=True)
class Sample:
    flow: str
    risk: str
    minutes: float
    usd: float
    title: str = ""
    task_id: str = ""


def read_samples(paths: WorksPaths) -> list[Sample]:
    samples: list[Sample] = []
    if not paths.runs.exists():
        return samples
    for path in sorted(paths.runs.glob("*/evidence.json")):
        try:
            evidence = Evidence.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if evidence.duration_ms <= 0:
            continue
        risk = evidence.risk.level.value if evidence.risk is not None else "medium"
        samples.append(
            Sample(
                flow=evidence.flow,
                risk=str(risk),
                minutes=evidence.duration_ms / 60_000.0,
                usd=float(evidence.usd),
                task_id=evidence.task_id,
            )
        )
    return samples


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * min(max(q, 0.0), 1.0)
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def group_key(flow: str, risk: str) -> str:
    return f"{flow}|{risk}"


def estimate_from(samples: list[Sample], *, source: str = "history") -> Estimate:
    minutes = [sample.minutes for sample in samples]
    money = [sample.usd for sample in samples]
    return Estimate(
        p50_min=quantile(minutes, 0.5),
        p90_min=quantile(minutes, 0.9),
        p50_usd=quantile(money, 0.5),
        p90_usd=quantile(money, 0.9),
        confidence=min(1.0, len(samples) / 20.0),
        samples=len(samples),
        source=source,
    )


def group_estimates(
    samples: list[Sample],
    *,
    min_samples: int = 5,
) -> dict[str, Estimate]:
    groups: dict[str, list[Sample]] = {}
    for sample in samples:
        groups.setdefault(group_key(sample.flow, sample.risk), []).append(sample)
    return {
        key: estimate_from(values) for key, values in groups.items() if len(values) >= min_samples
    }


def history_map(
    paths: WorksPaths,
    *,
    min_samples: int = 5,
) -> dict[str, Estimate]:
    return group_estimates(read_samples(paths), min_samples=min_samples)


def backtest(samples: list[Sample], *, min_samples: int = 5) -> dict[str, float | int]:
    """Leave-one-out coverage and pinball loss for the history estimator itself."""
    groups: dict[str, list[Sample]] = {}
    for sample in samples:
        groups.setdefault(group_key(sample.flow, sample.risk), []).append(sample)
    covered = 0
    total = 0
    loss = 0.0
    for values in groups.values():
        if len(values) < min_samples + 1:
            continue
        for index, actual in enumerate(values):
            others = values[:index] + values[index + 1 :]
            estimate = estimate_from(others)
            total += 1
            if actual.minutes <= estimate.p90_min:
                covered += 1
            for q, predicted in ((0.5, estimate.p50_min), (0.9, estimate.p90_min)):
                error = actual.minutes - predicted
                loss += max(q * error, (q - 1) * error)
    coverage = covered / total if total else 0.0
    return {
        "samples": total,
        "coverage_p90": coverage,
        "pinball": loss / (total * 2) if total else 0.0,
    }


_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    {"the", "a", "an", "and", "or", "to", "of", "in", "is", "it", "on", "for", "with"}
)


def tokens(title: str) -> set[str]:
    return {word for word in _WORD.findall(title.lower()) if word not in _STOP and len(word) > 2}


def similarity(left: str, right: str) -> float:
    one, two = tokens(left), tokens(right)
    if not one or not two:
        return 0.0
    return len(one & two) / len(one | two)


def knn_estimate(
    samples: list[Sample],
    *,
    title: str,
    flow: str,
    risk: str,
    k: int = 8,
    min_samples: int = 3,
) -> Estimate | None:
    """Neighbour quantiles: same flow/risk plus title overlap, no service and no embeddings."""
    scored: list[tuple[float, Sample]] = []
    for sample in samples:
        if not sample.title:
            continue
        score = similarity(title, sample.title)
        if sample.flow == flow:
            score += 0.5
        if sample.risk == risk:
            score += 0.25
        if score > 0:
            scored.append((score, sample))
    scored.sort(key=lambda item: item[0], reverse=True)
    chosen = [sample for _score, sample in scored[:k]]
    if len(chosen) < min_samples:
        return None
    return estimate_from(chosen, source="knn")


def titled_samples(paths: WorksPaths) -> list[Sample]:
    titles = {task.id: task.source.title for task in Queue(paths).list_tasks()}
    return [
        Sample(
            flow=sample.flow,
            risk=sample.risk,
            minutes=sample.minutes,
            usd=sample.usd,
            title=titles.get(sample.task_id, ""),
            task_id=sample.task_id,
        )
        for sample in read_samples(paths)
    ]
