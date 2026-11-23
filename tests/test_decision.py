from __future__ import annotations

import sys
import types

import pytest

from works.application.approvals.decisions import (
    DeterministicGate,
    GateContext,
    LaixGate,
    ShadowGate,
    build_decision_port,
)
from works.domain.errors import ConfigError
from works.domain.risk import RiskLevel


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

    monkeypatch.setattr("works.application.approvals.decisions.LaixGate", BrokenLaix)
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


def test_laix_gate_maps_a_decision(monkeypatch) -> None:
    module = types.ModuleType("laix")

    class Option:
        def __init__(self, **values) -> None:
            self.__dict__.update(values)

    class Decision:
        verb = "act"
        reason_code = "policy_rule"
        confidence = 0.99
        requires_approval = True
        decision_id = "DEC-1"
        trace_id = "TRC-1"
        alternatives = (types.SimpleNamespace(action_id="ask"),)

        def to_dict(self) -> dict:
            return {"verb": self.verb, "reason_code": self.reason_code}

    module.ActionOption = Option
    module.Belief = Option
    module.DecisionRequest = Option
    module.Situation = Option
    module.decide = lambda request: [Decision()]
    monkeypatch.setitem(sys.modules, "laix", module)

    gate = LaixGate()
    verdict = gate.decide(context(gate="release"))
    assert verdict.source == "laix"
    assert verdict.verb == "act"
    assert verdict.action == "ask"
    assert verdict.decision_id == "DEC-1"
    assert verdict.alternatives == ["ask"]


def test_shadow_records_a_successful_laix_decision(monkeypatch) -> None:
    module = types.ModuleType("laix")

    class Option:
        def __init__(self, **values) -> None:
            self.__dict__.update(values)

    class Decision:
        verb = "act"
        reason_code = "policy_rule"
        confidence = 0.99
        requires_approval = True
        decision_id = "DEC-2"
        trace_id = "TRC-2"
        alternatives = ()

        def to_dict(self) -> dict:
            return {"verb": self.verb}

    module.ActionOption = Option
    module.Belief = Option
    module.DecisionRequest = Option
    module.Situation = Option
    module.decide = lambda request: [Decision()]
    monkeypatch.setitem(sys.modules, "laix", module)

    gate = ShadowGate()
    verdict = gate.decide(context(gate="release"))
    assert verdict.source == "deterministic"
    assert gate.last_shadow is not None
    assert gate.agrees(verdict) is False
