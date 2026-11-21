"""The decision port: deterministic by default, LAIX optional, shadow first."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from .errors import ConfigError, WorksError
from .records import SCHEMA_VERSION
from .risk import RiskLevel

MODES = ("off", "shadow", "laix")


class GateContext(BaseModel):
    task_id: str
    gate: str
    base_commit: str | None = None
    risk: RiskLevel = RiskLevel.MEDIUM
    policy_ok: bool = True
    verdict_allow: bool | None = None
    challenge_allow: bool | None = None
    already_approved: bool = False
    touched_paths: list[str] = Field(default_factory=list)
    diff_lines: int = 0
    budget_usd_left: float = 0.0
    attention_budget: int = 3
    evidence: list[str] = Field(default_factory=list)


class GateVerdict(BaseModel):
    schema_version: int = SCHEMA_VERSION
    verb: str
    action: str
    reason_code: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_approval: bool = False
    decision_id: str = ""
    trace_id: str = ""
    alternatives: list[str] = Field(default_factory=list)
    source: str = "deterministic"
    raw: dict[str, Any] = Field(default_factory=dict)


class DecisionPort(Protocol):
    mode: str

    def decide(self, context: GateContext) -> GateVerdict: ...


class DeterministicGate:
    """The fallback: current rules, no dependency, never fails open."""

    mode = "off"

    def decide(self, context: GateContext) -> GateVerdict:
        if context.gate == "plan":
            if context.already_approved:
                return GateVerdict(
                    verb="act",
                    action="allow",
                    reason_code="already_approved",
                    confidence=0.99,
                    requires_approval=False,
                )
            return GateVerdict(
                verb="ask",
                action="ask",
                reason_code="plan_needs_person",
                confidence=0.95,
                requires_approval=True,
            )
        if not context.policy_ok:
            return GateVerdict(
                verb="escalate",
                action="escalate",
                reason_code="policy_violation",
                confidence=0.99,
                requires_approval=True,
            )
        if context.verdict_allow is False:
            return GateVerdict(
                verb="verify",
                action="verify",
                reason_code="verdict_blocked",
                confidence=0.99,
                requires_approval=True,
            )
        if context.risk is RiskLevel.HIGH:
            return GateVerdict(
                verb="ask",
                action="ask",
                reason_code="high_risk",
                confidence=0.9,
                requires_approval=True,
            )
        return GateVerdict(
            verb="act",
            action="allow",
            reason_code="evidence_sufficient",
            confidence=0.9,
            requires_approval=True,
        )


class LaixGate:
    """The optional adapter. LAIX decides a verb; Works still enforces the gate."""

    mode = "laix"

    def __init__(self) -> None:
        try:
            from laix import (  # type: ignore[import-not-found]
                ActionOption,
                Belief,
                DecisionRequest,
                Situation,
                decide,
            )
        except ImportError as exc:
            raise ConfigError(
                "LAIX is not installed; install it with "
                "`pip install -e C:\\Workspace\\laix\\packages\\python\\laix`"
            ) from exc
        self._ActionOption = ActionOption
        self._Belief = Belief
        self._DecisionRequest = DecisionRequest
        self._Situation = Situation
        self._decide = decide

    def decide(self, context: GateContext) -> GateVerdict:
        at = datetime.now(tz=UTC).isoformat()
        risk_value = {"low": 0.15, "medium": 0.45, "high": 0.85}[context.risk.value]
        beliefs = tuple(
            self._Belief(id=f"evidence-{index}", proposition=text, confidence=0.9)
            for index, text in enumerate(context.evidence)
        )
        situation = self._Situation(
            id=f"{context.task_id}-{context.gate}",
            at=at,
            subject=f"{context.gate} gate for {context.task_id}",
            beliefs=beliefs,
            attributes={"risk": risk_value, "urgency": 0.6, "uncertainty": 0.1},
        )
        options = (
            self._ActionOption(
                id="act",
                verb="act",
                name="proceed",
                expected_benefit=0.9,
                risk=risk_value,
                reversible=context.risk is not RiskLevel.HIGH,
                requires_approval=True,
            ),
            self._ActionOption(
                id="ask",
                verb="ask",
                name="ask the owner",
                expected_benefit=0.8,
                interrupt_cost=0.2,
            ),
            self._ActionOption(
                id="wait",
                verb="wait",
                name="wait for more evidence",
                expected_benefit=0.3,
                interrupt_cost=0.0,
            ),
            self._ActionOption(
                id="verify",
                verb="verify",
                name="verify again",
                expected_benefit=0.6,
                risk=risk_value,
            ),
            self._ActionOption(
                id="escalate",
                verb="escalate",
                name="escalate",
                expected_benefit=0.5,
                interrupt_cost=0.4,
            ),
        )
        request = self._DecisionRequest(
            subject=f"{context.gate} gate for {context.task_id}",
            at=at,
            situation=situation,
            options=options,
            attributes={"urgency": 0.6, "uncertainty": 0.1},
        )
        decision = self._decide(request)[0]
        verb = str(decision.verb)
        action = {
            "act": "allow" if not decision.requires_approval else "ask",
            "guide": "ask",
            "ask": "ask",
            "wait": "wait",
            "observe": "wait",
            "verify": "verify",
            "escalate": "escalate",
        }.get(verb, "ask")
        return GateVerdict(
            verb=verb,
            action=action,
            reason_code=str(decision.reason_code),
            confidence=float(decision.confidence),
            requires_approval=bool(decision.requires_approval),
            decision_id=str(decision.decision_id),
            trace_id=str(decision.trace_id),
            alternatives=[str(item.action_id) for item in decision.alternatives],
            source="laix",
            raw=dict(decision.to_dict()),
        )


class ShadowGate:
    """Compute both; execute the deterministic one and keep the difference."""

    mode = "shadow"

    def __init__(self) -> None:
        self._primary = DeterministicGate()
        self._shadow: DecisionPort | None = None
        self.last_shadow: GateVerdict | None = None
        self.last_error: str | None = None

    def decide(self, context: GateContext) -> GateVerdict:
        primary = self._primary.decide(context)
        self.last_shadow = None
        self.last_error = None
        try:
            if self._shadow is None:
                self._shadow = LaixGate()
            self.last_shadow = self._shadow.decide(context)
        except (WorksError, ImportError, AttributeError, TypeError, ValueError) as exc:
            self.last_error = str(exc)
        return primary

    def agrees(self, primary: GateVerdict) -> bool | None:
        if self.last_shadow is None:
            return None
        return primary.action == self.last_shadow.action


def build_decision_port(mode: str | None = None) -> DecisionPort:
    selected = (mode or os.environ.get("WORKS_DECISION") or "off").lower()
    if selected not in MODES:
        raise ConfigError(f"unknown decision mode {selected!r}; expected off, shadow or laix")
    if selected == "shadow":
        return ShadowGate()
    if selected == "laix":
        return LaixGate()
    return DeterministicGate()
