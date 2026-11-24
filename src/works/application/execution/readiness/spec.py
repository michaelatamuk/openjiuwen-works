"""Readiness gate internals.

The public API is re-exported from the package ``__init__`` so callers keep using
``works.application.execution.readiness``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from works.domain.errors import ConfigError

CheckStatus = Literal["pass", "fail", "skip"]


ReportStatus = Literal["pass", "fail", "partial"]


SPEC_PATH = Path(".works/readiness.yaml")


COMMANDS = (
    ("lint", "Lint"),
    ("format", "Format"),
    ("types", "Types"),
    ("tests", "Fast tests"),
    ("verify", "Product verify"),
    ("architecture", "Architecture boundaries"),
)


class Commands(BaseModel):
    lint: str | None = None
    format: str | None = None
    types: str | None = None
    tests: str | None = None
    verify: str | None = None
    architecture: str | None = None


class Suppressions(BaseModel):
    allow: list[str] = Field(default_factory=list)


class BoundaryRule(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(alias="from", min_length=1)
    deny: list[str] = Field(default_factory=list)


class Boundaries(BaseModel):
    rules: list[BoundaryRule] = Field(default_factory=list)


class ReadinessSpec(BaseModel):
    schema_version: int = 1
    features: str = "features"
    commands: Commands = Field(default_factory=Commands)
    suppressions: Suppressions = Field(default_factory=Suppressions)
    boundaries: Boundaries = Field(default_factory=Boundaries)


@dataclass(frozen=True)
class CheckResult:
    id: str
    label: str
    status: CheckStatus
    detail: str = ""

    @property
    def ok(self) -> bool | None:
        if self.status == "skip":
            return None
        return self.status == "pass"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "ok": self.ok,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SuppressionFinding:
    location: str
    kind: str
    text: str

    def as_dict(self) -> dict[str, str]:
        return {"location": self.location, "kind": self.kind, "text": self.text}


@dataclass
class ReadinessReport:
    status: ReportStatus
    checks: list[CheckResult]
    passed: int
    failed: int
    skipped: int
    total: int
    suppressions: list[SuppressionFinding] = field(default_factory=list)
    unknown_suppressions: list[SuppressionFinding] = field(default_factory=list)
    feature_files: list[str] = field(default_factory=list)
    import_cycles: list[list[str]] = field(default_factory=list)
    import_edges: dict[str, list[str]] = field(default_factory=dict)
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": True,
            "status": self.status,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "total": self.total,
            "checks": [check.as_dict() for check in self.checks],
            "suppressions": [item.as_dict() for item in self.suppressions],
            "unknown_suppressions": [item.as_dict() for item in self.unknown_suppressions],
            "features": self.feature_files,
            "import_cycles": self.import_cycles,
            "import_edges": self.import_edges,
            "note": self.note,
        }


def load_spec(repo: Path) -> ReadinessSpec | None:
    path = repo / SPEC_PATH
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read {SPEC_PATH}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{SPEC_PATH} must be a mapping")
    try:
        return ReadinessSpec.model_validate(raw)
    except Exception as exc:
        raise ConfigError(f"{SPEC_PATH} is invalid: {exc}") from exc
