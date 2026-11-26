"""Risk rating decides the evidence and the reviewers. It never opens or closes a gate."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from works.adapters.git.repo import DiffStat
from works.domain.flow import FlowSpec
from works.domain.policy import matches
from works.domain.records import SCHEMA_VERSION

# A change is heavy when one file carries more than this many changed lines.
HEAVY_FILE_LINES = 200
# Named in reasons so the page stays readable; the full list is in `security_paths`.
MAX_NAMED_PATHS = 3


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
    max_file_churn: int = 0
    heavy_files: int = 0
    security_paths: list[str] = Field(default_factory=list)

    @property
    def requires_owner(self) -> bool:
        return bool(self.owners)

    def summary_line(self) -> str:
        """One line for a card: the level, the size and the sharpest reason."""
        reason = self.reasons[0] if self.reasons else "no high-risk path"
        return f"{self.level.value} · {self.files} file(s), {self.lines} line(s) · {reason}"


def _named(paths: list[str]) -> str:
    if len(paths) <= MAX_NAMED_PATHS:
        return ", ".join(paths)
    rest = len(paths) - MAX_NAMED_PATHS
    return f"{', '.join(paths[:MAX_NAMED_PATHS])} and {rest} more"


def rate_risk(
    *,
    paths: list[str],
    diff_stat: list[DiffStat],
    flow: FlowSpec,
    coverage: float | None = None,
    recent_incidents: int = 0,
) -> RiskRating:
    high_patterns = list(flow.risk.high_paths)
    sensitive_patterns = list(flow.risk.sensitive_paths)
    high = [path for path in paths if matches(path, high_patterns)]
    sensitive = [path for path in paths if matches(path, sensitive_patterns)]
    security = [path for path in sensitive if path not in high]
    churn = [max(stat.added, 0) + max(stat.removed, 0) for stat in diff_stat]
    heavy = [stat for stat, size in zip(diff_stat, churn, strict=True) if size > HEAVY_FILE_LINES]
    lines = sum(churn)
    max_file_churn = max(churn, default=0)
    docs_only = bool(paths) and all(
        path.endswith(".md") or path.startswith("docs/") for path in paths
    )

    reasons: list[str] = []
    if high:
        reasons.append(f"critical path: {_named(sorted(high))}")
    if security:
        reasons.append(f"security-sensitive path: {_named(sorted(security))}")
    if docs_only:
        reasons.append("documentation only")
    if len(paths) > 10:
        reasons.append(f"{len(paths)} files changed")
    if lines > 400:
        reasons.append(f"{lines} lines changed")
    if heavy:
        reasons.append(f"{len(heavy)} file(s) over {HEAVY_FILE_LINES} changed lines")
    if coverage is not None and coverage < 0.8:
        reasons.append(f"coverage {coverage:.0%} is below 80%")
    if recent_incidents:
        reasons.append(f"{recent_incidents} recent incident(s) on these paths")

    if high or security or recent_incidents:
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
        rounded_up=bool(high or security or recent_incidents),
        files=len(paths),
        lines=lines,
        max_file_churn=max_file_churn,
        heavy_files=len(heavy),
        security_paths=sorted(sensitive),
    )
