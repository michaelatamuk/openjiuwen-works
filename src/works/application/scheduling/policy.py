"""The scheduler policy: one file, strict, off by default.

`<home>/config/dispatch.yaml` is the only source of truth for "what may run". A missing file means
"disabled", not "run everything"; an invalid file is a `config_error` at load, never a partial
apply.
"""

from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from works.config.paths import WorksPaths
from works.domain.errors import ConfigError

Level = Literal["L1", "L2", "L3"]
Risk = Literal["low", "medium", "high", "critical"]
POLICY_PATH = Path("config") / "dispatch.yaml"
LEVELS: tuple[Level, ...] = ("L1", "L2", "L3")
RISK_ORDER: tuple[Risk, ...] = ("low", "medium", "high", "critical")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Levels(_Strict):
    default: Level = "L1"
    by_source: dict[str, Level] = Field(default_factory=dict)


class Allow(_Strict):
    sources: list[str] = Field(default_factory=lambda: ["github", "jira", "detector"])
    labels: list[str] = Field(default_factory=lambda: ["works:auto"])
    labels_deny: list[str] = Field(default_factory=lambda: ["works:hold"])
    manual: bool = False
    flows: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    repos: list[str] = Field(default_factory=list)
    remote_triggers: bool = False
    risk_max_for_L2: Risk = "medium"
    risk_max_for_L3: Risk = "medium"


class Concurrency(_Strict):
    global_slots: int = Field(2, alias="global", ge=1)
    per_repo: int = Field(1, ge=1)


class BudgetPolicy(_Strict):
    daily_usd: float | None = Field(None, gt=0)
    per_run_usd: float = Field(5.0, gt=0)
    on_exhausted: Literal["skip", "pause"] = "skip"


class QueuePolicy(_Strict):
    max_age_hours: float = Field(72, gt=0)
    max_attempts: int = Field(2, ge=1)
    backoff_seconds: int = Field(300, ge=0)
    starvation_boost_hours: float = Field(24, ge=0)


class Resources(_Strict):
    pause_when_job_pool_pct: float = Field(80, ge=0, le=100)
    pause_when_api_p95_ms: float = Field(300, gt=0)
    min_free_disk_gb: float = Field(5, ge=0)
    pause_on_provider_errors: int = Field(3, ge=1)


class Attention(_Strict):
    max_waiting_plans: int = Field(3, ge=1)


class Windows(_Strict):
    blackout: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _windows(self) -> Windows:
        for raw in self.blackout:
            parse_window(raw)
        return self


class Estimates(_Strict):
    source: Literal["history", "plan", "static"] = "static"
    min_samples: int = Field(5, ge=1)
    max_wall_clock_minutes: int = Field(90, ge=1)


class SizeBuckets(_Strict):
    small_max_minutes: float = Field(15, gt=0)
    large_min_minutes: float = Field(45, gt=0)


class Order(_Strict):
    mode: Literal["rule", "shadow", "learned"] = "rule"


class Priority(_Strict):
    order: list[str] = Field(
        default_factory=lambda: ["risk", "budget_fragility", "starvation", "size", "age"]
    )
    size_buckets: SizeBuckets = Field(default_factory=SizeBuckets)


class DispatchPolicy(_Strict):
    enabled: bool = False
    paused: bool = False
    tick_seconds: int = Field(10, ge=1)
    levels: Levels = Field(default_factory=Levels)
    allow: Allow = Field(default_factory=Allow)
    concurrency: Concurrency = Field(default_factory=Concurrency)
    budget: BudgetPolicy = Field(default_factory=BudgetPolicy)
    queue: QueuePolicy = Field(default_factory=QueuePolicy)
    resources: Resources = Field(default_factory=Resources)
    attention: Attention = Field(default_factory=Attention)
    windows: Windows = Field(default_factory=Windows)
    estimates: Estimates = Field(default_factory=Estimates)
    priority: Priority = Field(default_factory=Priority)
    order: Order = Field(default_factory=Order)


def policy_path(paths: WorksPaths) -> Path:
    return paths.root / POLICY_PATH


def load_policy(paths: WorksPaths) -> DispatchPolicy:
    """A missing file is a disabled policy; a broken file is a typed error."""
    path = policy_path(paths)
    if not path.exists():
        return DispatchPolicy()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    if raw is None:
        return DispatchPolicy()
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must be a mapping, got {type(raw).__name__}")
    try:
        policy = DispatchPolicy.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{path} is not a valid dispatch policy: {exc}") from exc
    if policy.order.mode == "learned":
        raise ConfigError("learned ordering is not available in this build; use order.mode: shadow")
    return policy


def parse_window(raw: str) -> tuple[time, time]:
    """`HH:MM-HH:MM`, local time. A window may wrap midnight (22:00-02:00)."""
    text = raw.strip()
    if "-" not in text:
        raise ValueError(f"window must look like HH:MM-HH:MM, got {raw!r}")
    start_raw, end_raw = text.split("-", 1)
    try:
        start = time.fromisoformat(start_raw.strip())
        end = time.fromisoformat(end_raw.strip())
    except ValueError as exc:
        raise ValueError(f"window must look like HH:MM-HH:MM, got {raw!r}") from exc
    return start, end


def inside_window(now: datetime, raw: str) -> bool:
    start, end = parse_window(raw)
    current = now.time()
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def in_blackout(policy: DispatchPolicy, now: datetime) -> bool:
    return any(inside_window(now, raw) for raw in policy.windows.blackout)


def level_for(policy: DispatchPolicy, source: str) -> Level:
    return policy.levels.by_source.get(source, policy.levels.default)


def risk_rank(risk: Risk) -> int:
    return RISK_ORDER.index(risk)


_SEVERITY: dict[str, Risk] = {
    "S1": "critical",
    "S2": "high",
    "S3": "medium",
    "S4": "low",
}


def risk_for_severity(severity: str | None) -> Risk:
    return _SEVERITY.get(severity or "", "medium")


def set_enabled(paths: WorksPaths, enabled: bool) -> Path:
    """Flip `enabled` while keeping the rest of the file and its comments intact."""
    path = policy_path(paths)
    value = "true" if enabled else "false"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"enabled: {value}\n", encoding="utf-8")
        return path
    lines = path.read_text(encoding="utf-8").splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.strip().startswith("enabled:"):
            lines[index] = f"enabled: {value}"
            replaced = True
            break
    if not replaced:
        lines.insert(0, f"enabled: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
