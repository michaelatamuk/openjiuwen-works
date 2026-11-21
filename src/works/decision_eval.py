"""Replay historical gate cases through the deterministic rule and a candidate decision layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .decision import DecisionPort, DeterministicGate, GateContext, GateVerdict
from .errors import ConfigError
from .records import SCHEMA_VERSION
from .risk import RiskLevel


class DecisionCase(BaseModel):
    schema_version: int = SCHEMA_VERSION
    id: str = Field(min_length=1)
    gate: str = "release"
    risk: RiskLevel = RiskLevel.MEDIUM
    required_reviewers: int = 1
    owners: list[str] = Field(default_factory=list)
    policy_ok: bool = True
    verdict_allow: bool | None = True
    challenge_allow: bool | None = True
    already_approved: bool = False
    evidence: list[str] = Field(default_factory=list)

    def context(self) -> GateContext:
        return GateContext(
            task_id=self.id,
            gate=self.gate,
            risk=self.risk,
            required_reviewers=self.required_reviewers,
            owners=self.owners,
            policy_ok=self.policy_ok,
            verdict_allow=self.verdict_allow,
            challenge_allow=self.challenge_allow,
            already_approved=self.already_approved,
            evidence=self.evidence,
        )


class DecisionOutcome(BaseModel):
    schema_version: int = SCHEMA_VERSION
    case_id: str
    deterministic: GateVerdict
    candidate: GateVerdict
    agree: bool
    unsafe_allow: bool


def load_cases(path: Path) -> list[DecisionCase]:
    if not path.exists():
        raise ConfigError(f"decision cases not found: {path}")
    cases: list[DecisionCase] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(DecisionCase.model_validate_json(line))
        except ValidationError as exc:
            raise ConfigError(f"{path}:{number} is not a valid decision case: {exc}") from exc
    if not cases:
        raise ConfigError(f"{path} contains no decision cases")
    return cases


def replay(cases: list[DecisionCase], candidate: DecisionPort) -> list[DecisionOutcome]:
    baseline = DeterministicGate()
    outcomes: list[DecisionOutcome] = []
    for case in cases:
        context = case.context()
        expected = baseline.decide(context)
        actual = candidate.decide(context)
        unsafe = actual.action == "allow" and (not case.policy_ok or case.verdict_allow is False)
        outcomes.append(
            DecisionOutcome(
                case_id=case.id,
                deterministic=expected,
                candidate=actual,
                agree=expected.action == actual.action,
                unsafe_allow=unsafe,
            )
        )
    return outcomes


def summary(outcomes: list[DecisionOutcome]) -> dict[str, Any]:
    return {
        "cases": len(outcomes),
        "agree": sum(1 for item in outcomes if item.agree),
        "disagree": sum(1 for item in outcomes if not item.agree),
        "unsafe_allow": sum(1 for item in outcomes if item.unsafe_allow),
        "outcomes": [item.model_dump(mode="json") for item in outcomes],
    }
