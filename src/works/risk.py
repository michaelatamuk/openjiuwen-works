"""Risk rating decides the evidence and the reviewers. It never opens or closes a gate."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .flow import FlowSpec
from .gitops import DiffStat
from .policy import matches
from .records import SCHEMA_VERSION


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskRating(BaseModel):
    schema_version: int = SCHEMA_VERSION
    level: RiskLevel
    reasons: list[str] = Field(default_factory=list)
    owners: list[str] = Field(default_factory=list)
    rounded_up: bool = False
    files: int = 0
    lines: int = 0

    @property
    def requires_owner(self) -> bool:
        return bool(self.owners)


def rate_risk(
    *,
    paths: list[str],
    diff_stat: list[DiffStat],
    flow: FlowSpec,
) -> RiskRating:
    high_patterns = list(flow.risk.high_paths)
    high = [path for path in paths if matches(path, high_patterns)]
    lines = sum(max(stat.added, 0) + max(stat.removed, 0) for stat in diff_stat)
    docs_only = bool(paths) and all(
        path.endswith(".md") or path.startswith("docs/") for path in paths
    )

    reasons: list[str] = []
    if high:
        reasons.append(f"critical path: {', '.join(sorted(high))}")
    if docs_only:
        reasons.append("documentation only")
    if len(paths) > 10:
        reasons.append(f"{len(paths)} files changed")
    if lines > 400:
        reasons.append(f"{lines} lines changed")

    if high:
        level = RiskLevel.HIGH
    elif docs_only or (len(paths) <= 1 and lines <= 20):
        level = RiskLevel.LOW
    else:
        level = RiskLevel.MEDIUM

    owners: set[str] = set()
    for pattern, names in flow.risk.owners.items():
        if any(matches(path, [pattern]) for path in paths):
            owners.update(names)
    if level is RiskLevel.HIGH and not owners:
        owners.add("owner")

    return RiskRating(
        level=level,
        reasons=reasons or ["no high-risk path and a bounded change"],
        owners=sorted(owners),
        rounded_up=bool(high),
        files=len(paths),
        lines=lines,
    )
