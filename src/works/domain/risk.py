"""Risk rating decides the evidence and the reviewers. It never opens or closes a gate."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from works.adapters.git.repo import DiffStat
from works.domain.flow import FlowSpec
from works.domain.policy import matches
from works.domain.records import SCHEMA_VERSION


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskRating(BaseModel):
    schema_version: int = SCHEMA_VERSION
    level: RiskLevel
    reasons: list[str] = Field(default_factory=list)
    owners: list[str] = Field(default_factory=list)
    required_reviewers: int = 1
    deeper_verification: bool = False
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
    coverage: float | None = None,
    recent_incidents: int = 0,
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
    if coverage is not None and coverage < 0.8:
        reasons.append(f"coverage {coverage:.0%} is below 80%")
    if recent_incidents:
        reasons.append(f"{recent_incidents} recent incident(s) on these paths")

    if high or recent_incidents:
        level = RiskLevel.HIGH
    elif docs_only or (len(paths) <= 1 and lines <= 20 and (coverage is None or coverage >= 0.8)):
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
        required_reviewers=1 if level is RiskLevel.LOW else 2,
        deeper_verification=level is RiskLevel.HIGH,
        rounded_up=bool(high or recent_incidents),
        files=len(paths),
        lines=lines,
    )
