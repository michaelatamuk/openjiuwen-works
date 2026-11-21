from __future__ import annotations

import pytest

from works.decision import (
    DeterministicGate,
    GateContext,
    ShadowGate,
    build_decision_port,
)
from works.errors import ConfigError
from works.risk import RiskLevel


def context(**overrides) -> GateContext:
    values = {
        "task_id": "t-1",
        "gate": "plan",
        "base_commit": "abc",
        "risk": RiskLevel.LOW,
        "policy_ok": True,
        "verdict_allow": True,
        "challenge_allow": True,
        "already_approved": False,
        "touched_paths": ["calc/core.py"],
        "diff_lines": 2,
        "budget_usd_left": 9.0,
        "evidence": ["the reproduction failed on the base commit"],
    }
    values.update(overrides)
    return GateContext(**values)


def test_deterministic_plan_asks_for_a_person() -> None:
    verdict = DeterministicGate().decide(context())
    assert verdict.action == "ask"
    assert verdict.requires_approval is True
    assert verdict.reason_code == "plan_needs_person"


def test_an_approved_plan_is_an_act() -> None:
    verdict = DeterministicGate().decide(context(already_approved=True))
    assert verdict.action == "allow"
    assert verdict.reason_code == "already_approved"


def test_a_policy_violation_escalates() -> None:
    verdict = DeterministicGate().decide(context(gate="release", policy_ok=False))
    assert verdict.verb == "escalate"
    assert verdict.action == "escalate"


def test_a_blocked_verdict_asks_for_verification() -> None:
    verdict = DeterministicGate().decide(context(gate="release", verdict_allow=False))
    assert verdict.verb == "verify"
    assert verdict.action == "verify"


def test_high_risk_release_asks_a_person() -> None:
    verdict = DeterministicGate().decide(context(gate="release", risk=RiskLevel.HIGH))
    assert verdict.verb == "ask"
    assert verdict.requires_approval is True


def test_shadow_keeps_the_deterministic_answer_when_laix_is_absent(monkeypatch) -> None:
    class BrokenLaix:
        def __init__(self) -> None:
            raise ConfigError("absent")

    monkeypatch.setattr("works.decision.LaixGate", BrokenLaix)
    gate = ShadowGate()
    verdict = gate.decide(context(gate="release"))
    assert verdict.source == "deterministic"
    assert verdict.action == "allow"
    assert gate.last_error is not None


def test_unknown_decision_mode_is_refused() -> None:
    with pytest.raises(ConfigError):
        build_decision_port("sometimes")


def test_off_is_the_default(monkeypatch) -> None:
    monkeypatch.delenv("WORKS_DECISION", raising=False)
    gate = build_decision_port()
    assert gate.mode == "off"
