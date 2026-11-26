"""Estimates from stored evidence: p50/p90, confidence, never a promise.

The scheduler needs to know whether a run fits a budget or a window, and which of two equal-risk
tasks is shorter. It does not need a deadline. This module reads `runs/*/evidence.json`, joins each
sample with the task it came from, and offers four estimators: grouped history, similar tasks (BM25
over titles plus label/path overlap), the planner's own estimate, and a static prior.
"""

from __future__ import annotations

import math
import re
from collections import Counter
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
    plan_minutes: float = 0.0
    plan_usd: float = 0.0
    labels: frozenset[str] = frozenset()
    paths: frozenset[str] = frozenset()
    source: str = ""


@dataclass(frozen=True)
class Features:
    title: str = ""
    flow: str = ""
    risk: str = "medium"
    labels: frozenset[str] = frozenset()
    paths: frozenset[str] = frozenset()
    source: str = ""


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
                plan_minutes=float(evidence.plan_estimated_minutes),
                plan_usd=float(evidence.plan_estimated_usd),
            )
        )
    return samples


def enriched_samples(paths: WorksPaths) -> list[Sample]:
    """Join each run with its task: title, labels, source and the paths it was allowed to touch."""
    tasks = {task.id: task for task in Queue(paths).list_tasks()}
    enriched: list[Sample] = []
    for sample in read_samples(paths):
        task = tasks.get(sample.task_id)
        if task is None:
            enriched.append(sample)
            continue
        source = (task.source.channel or "").strip().lower() or task.source.kind.value
        enriched.append(
            Sample(
                flow=sample.flow,
                risk=sample.risk,
                minutes=sample.minutes,
                usd=sample.usd,
                title=task.source.title,
                task_id=sample.task_id,
                plan_minutes=sample.plan_minutes,
                plan_usd=sample.plan_usd,
                labels=frozenset(task.source.labels),
                paths=frozenset(task.scope.paths_allow),
                source=source,
            )
        )
    return enriched


def titled_samples(paths: WorksPaths) -> list[Sample]:
    return enriched_samples(paths)


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


def estimate_from_plan(minutes: float, usd: float) -> Estimate | None:
    """The planner's own size estimate: one point, widened for the tail."""
    if minutes <= 0:
        return None
    return Estimate(
        p50_min=minutes,
        p90_min=minutes * 1.5,
        p50_usd=max(usd, 0.0),
        p90_usd=max(usd, 0.0) * 1.5,
        confidence=0.4,
        samples=0,
        source="plan",
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


def plan_map(
    samples: list[Sample],
    *,
    min_samples: int = 1,
) -> dict[str, Estimate]:
    """The planner's own size estimate, used only when history is thin."""
    groups: dict[str, list[Sample]] = {}
    for sample in samples:
        if sample.plan_minutes <= 0:
            continue
        planned = Sample(
            flow=sample.flow,
            risk=sample.risk,
            minutes=sample.plan_minutes,
            usd=sample.plan_usd,
        )
        groups.setdefault(group_key(sample.flow, sample.risk), []).append(planned)
    return {
        key: estimate_from(values, source="plan")
        for key, values in groups.items()
        if len(values) >= min_samples
    }


def history_map(
    paths: WorksPaths,
    *,
    min_samples: int = 5,
) -> dict[str, Estimate]:
    return group_estimates(read_samples(paths), min_samples=min_samples)


# --------------------------------------------------------------------------------------------------
# Similar tasks: BM25 over titles plus label and path overlap. No service, no embeddings.

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


def _jaccard(one: frozenset[str], two: frozenset[str]) -> float:
    if not one or not two:
        return 0.0
    return len(one & two) / len(one | two)


class Bm25:
    """A small BM25 index over titles; the score is normalised to 0..1 for one query."""

    def __init__(self, documents: list[set[str]]) -> None:
        self._documents = documents
        self._df: Counter[str] = Counter()
        for document in documents:
            self._df.update(document)
        self._size = len(documents)
        self._average = (
            sum(len(document) for document in documents) / self._size if self._size else 0.0
        )

    def score(self, query: set[str], index: int) -> float:
        document = self._documents[index]
        if not query or not document:
            return 0.0
        length = len(document)
        total = 0.0
        for term in query:
            frequency = 1 if term in document else 0
            if not frequency:
                continue
            df = self._df.get(term, 0)
            idf = math.log(1 + (self._size - df + 0.5) / (df + 0.5))
            denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * (length / self._average or 1))
            total += idf * (frequency * 2.5) / denominator
        return min(1.0, total / max(len(query), 1))


def knn_estimate(
    samples: list[Sample],
    *,
    title: str = "",
    flow: str = "",
    risk: str = "medium",
    labels: frozenset[str] = frozenset(),
    paths: frozenset[str] = frozenset(),
    source: str = "",
    k: int = 8,
    min_samples: int = 3,
) -> Estimate | None:
    """Neighbour quantiles from similar tickets, with the sample count as the explanation."""
    with_titles = [sample for sample in samples if sample.title]
    if len(with_titles) < min_samples:
        return None
    index = Bm25([tokens(sample.title) for sample in with_titles])
    query = tokens(title)
    scored: list[tuple[float, Sample]] = []
    for position, sample in enumerate(with_titles):
        score = 2.0 * index.score(query, position)
        score += _jaccard(labels, sample.labels)
        score += 1.5 * _jaccard(paths, sample.paths)
        if flow and sample.flow == flow:
            score += 0.5
        if sample.risk == risk:
            score += 0.25
        if source and sample.source == source:
            score += 0.25
        if score > 0:
            scored.append((score, sample))
    scored.sort(key=lambda item: item[0], reverse=True)
    chosen = [sample for _score, sample in scored[:k]]
    if len(chosen) < min_samples:
        return None
    return estimate_from(chosen, source="knn")


def backtest(samples: list[Sample], *, min_samples: int = 5) -> dict[str, object]:
    """Leave-one-out coverage, pinball loss, tail misses and the same per group."""
    groups: dict[str, list[Sample]] = {}
    for sample in samples:
        groups.setdefault(group_key(sample.flow, sample.risk), []).append(sample)
    covered = 0
    total = 0
    loss = 0.0
    tails = 0
    details: list[dict[str, object]] = []
    for key, values in groups.items():
        if len(values) < min_samples + 1:
            continue
        group_covered = 0
        group_total = 0
        group_loss = 0.0
        group_tails = 0
        for index, actual in enumerate(values):
            others = values[:index] + values[index + 1 :]
            estimate = estimate_from(others)
            group_total += 1
            if actual.minutes <= estimate.p90_min:
                group_covered += 1
            else:
                group_tails += 1
            for q, predicted in ((0.5, estimate.p50_min), (0.9, estimate.p90_min)):
                error = actual.minutes - predicted
                group_loss += max(q * error, (q - 1) * error)
        total += group_total
        covered += group_covered
        tails += group_tails
        loss += group_loss
        details.append(
            {
                "group": key,
                "samples": group_total,
                "coverage_p90": group_covered / group_total,
                "pinball": group_loss / (group_total * 2),
                "tail_misses": group_tails,
            }
        )
    return {
        "samples": total,
        "coverage_p90": covered / total if total else 0.0,
        "pinball": loss / (total * 2) if total else 0.0,
        "tail_misses": tails,
        "groups": details,
    }
