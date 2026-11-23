"""Feature maps: what a product promises, and what this proof actually exercised."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from works.domain.errors import ConfigError


class Feature(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    user_path: str = Field(min_length=1)
    expected: str = Field(min_length=1)
    scenario_ids: list[str] = Field(default_factory=list)
    selector: str | None = None
    command: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Feature:
        if not self.scenario_ids and not self.selector and not self.command:
            raise ValueError(f"feature {self.id!r} needs scenario_ids, a selector or a command")
        return self


class FeatureFile(BaseModel):
    schema_version: int = 1
    product: str
    features: list[Feature] = Field(default_factory=list)


class FeatureCoverage(BaseModel):
    id: str
    name: str
    user_path: str
    expected: str
    covered: bool
    passed: bool
    scenarios: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "user_path": self.user_path,
            "expected": self.expected,
            "covered": self.covered,
            "passed": self.passed,
            "scenarios": self.scenarios,
        }


def _root(repo: Path, root: str = "features") -> Path:
    return repo / root


def feature_files(repo: Path, root: str = "features") -> list[Path]:
    directory = _root(repo, root)
    if directory.is_file():
        return [directory]
    if not directory.exists():
        return []
    return sorted(path for path in directory.rglob("*") if path.suffix in (".yaml", ".yml"))


def load_feature_maps(repo: Path, root: str = "features") -> list[FeatureFile]:
    maps: list[FeatureFile] = []
    for path in feature_files(repo, root):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(f"cannot read feature map {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError(f"feature map {path} must be a mapping")
        try:
            maps.append(FeatureFile.model_validate(raw))
        except ValidationError as exc:
            raise ConfigError(f"feature map {path} is invalid: {exc}") from exc
    return maps


def coverage(maps: list[FeatureFile], evidence: dict[str, Any] | None) -> list[FeatureCoverage]:
    outcomes = ((evidence or {}).get("verdict") or {}).get("outcomes") or []
    by_id = {
        str(item.get("id")): bool(item.get("passed"))
        for item in outcomes
        if isinstance(item, dict) and item.get("id")
    }
    covered: list[FeatureCoverage] = []
    for feature_map in maps:
        for feature in feature_map.features:
            matched = [scenario for scenario in feature.scenario_ids if scenario in by_id]
            covered.append(
                FeatureCoverage(
                    id=feature.id,
                    name=feature.name,
                    user_path=feature.user_path,
                    expected=feature.expected,
                    covered=bool(matched),
                    passed=bool(matched) and all(by_id[scenario] for scenario in matched),
                    scenarios=matched,
                )
            )
    return covered


def feature_summary(
    repo: Path,
    evidence: dict[str, Any] | None = None,
    *,
    root: str = "features",
) -> dict[str, Any]:
    files = [path.name for path in feature_files(repo, root)]
    if not files:
        return {
            "available": False,
            "files": [],
            "features": [],
            "covered": 0,
            "total": 0,
            "uncovered": 0,
            "note": "No feature map yet. Add features/<product>.yaml (T2.19).",
        }
    try:
        maps = load_feature_maps(repo, root)
    except ConfigError as exc:
        return {
            "available": True,
            "files": files,
            "features": [],
            "covered": 0,
            "total": 0,
            "uncovered": 0,
            "error": str(exc),
            "note": "The feature map is invalid; fix it before relying on coverage.",
        }
    features = coverage(maps, evidence)
    covered = sum(1 for feature in features if feature.covered)
    passed = sum(1 for feature in features if feature.passed)
    return {
        "available": True,
        "files": files,
        "features": [feature.as_dict() for feature in features],
        "covered": covered,
        "passed": passed,
        "total": len(features),
        "uncovered": len(features) - covered,
        "note": (
            "Every feature is covered by this proof."
            if features and covered == len(features)
            else f"{len(features) - covered} feature(s) are not covered by this proof."
        ),
    }
