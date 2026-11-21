from __future__ import annotations

from pathlib import Path

from works.decision import DeterministicGate, GateContext, GateVerdict
from works.decision_eval import load_cases, replay, summary


class AllowAllGate:
    mode = "fake"

    def decide(self, context: GateContext) -> GateVerdict:
        return GateVerdict(
            verb="act",
            action="allow",
            reason_code="fake_allow",
            confidence=1.0,
            source="fake",
        )


def test_the_fixture_has_twenty_cases(factory_root: Path) -> None:
    cases = load_cases(factory_root / "fixtures" / "decision-cases.jsonl")
    assert len(cases) == 20
    assert {case.gate for case in cases} == {"plan", "release"}


def test_the_deterministic_rule_agrees_with_itself(factory_root: Path) -> None:
    cases = load_cases(factory_root / "fixtures" / "decision-cases.jsonl")
    outcomes = replay(cases, DeterministicGate())
    assert all(item.agree for item in outcomes)
    assert summary(outcomes)["unsafe_allow"] == 0


def test_an_allow_all_policy_is_caught(factory_root: Path) -> None:
    cases = load_cases(factory_root / "fixtures" / "decision-cases.jsonl")
    outcomes = replay(cases, AllowAllGate())
    assert any(item.unsafe_allow for item in outcomes)
    assert summary(outcomes)["unsafe_allow"] > 0
