"""Scenario sets: what the change is judged by. Written before the build."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from works.domain.errors import ConfigError
from works.domain.records import Priority, ScenarioOutcome, Verdict

P1_THRESHOLD = 0.8


class Scenario(BaseModel):
    id: str = Field(min_length=1)
    priority: Priority
    weight: float = Field(default=1.0, gt=0)
    description: str = ""
    script: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    timeout_s: int = Field(default=120, gt=0)

    def argv(self, python: str, directory: Path) -> list[str]:
        return [python, str((directory / self.script).resolve()), *self.args]


class ScenarioSet(BaseModel):
    schema_version: int = 1
    flow: str = "fix-issue"
    directory: str = "."
    scenarios: list[Scenario]

    @model_validator(mode="after")
    def _check(self) -> ScenarioSet:
        ids = [scenario.id for scenario in self.scenarios]
        if not ids:
            raise ValueError("a scenario set needs at least one scenario")
        if len(ids) != len(set(ids)):
            raise ValueError("scenario ids must be unique")
        if not any(scenario.priority is Priority.P0 for scenario in self.scenarios):
            raise ValueError("a scenario set needs at least one P0")
        return self

    @property
    def p0_ids(self) -> list[str]:
        return [s.id for s in self.scenarios if s.priority is Priority.P0]

    @property
    def p1_ids(self) -> list[str]:
        return [s.id for s in self.scenarios if s.priority is Priority.P1]


def load_scenario_set(path: Path) -> ScenarioSet:
    if not path.exists():
        raise ConfigError(f"scenario set not found: {path}")
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a mapping")
    try:
        scenario_set = ScenarioSet.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{path} is not a valid scenario set:\n{exc}") from exc
    directory = (path.parent / scenario_set.directory).resolve()
    for scenario in scenario_set.scenarios:
        script = (directory / scenario.script).resolve()
        if not script.exists():
            raise ConfigError(f"scenario {scenario.id!r} script not found: {script}")
    return scenario_set


def judge(outcomes: list[ScenarioOutcome], *, run_id: str) -> Verdict:
    """All P0 pass and P1 pass rate >= 80% allows; everything else blocks."""
    p0_failed = [
        outcome.id for outcome in outcomes if outcome.priority is Priority.P0 and not outcome.passed
    ]
    p1 = [outcome for outcome in outcomes if outcome.priority is Priority.P1]
    if p1:
        total = sum(outcome.weight for outcome in p1)
        passed = sum(outcome.weight for outcome in p1 if outcome.passed)
        p1_rate = passed / total if total else 1.0
    else:
        p1_rate = 1.0
    allow = not p0_failed and p1_rate >= P1_THRESHOLD
    if p0_failed:
        reason = f"failed P0: {', '.join(p0_failed)}"
    elif p1_rate < P1_THRESHOLD:
        reason = f"P1 pass rate {p1_rate:.0%} is below {P1_THRESHOLD:.0%}"
    else:
        reason = f"all P0 passed; P1 pass rate {p1_rate:.0%}"
    return Verdict(
        run_id=run_id,
        allow=allow,
        reason=reason,
        p0_failed=p0_failed,
        p1_pass_rate=round(p1_rate, 4),
        outcomes=sorted(outcomes, key=lambda item: item.id),
    )
