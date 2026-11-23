"""A deterministic verification team built on agent-core's BaseTeam + TeamRuntime.

The team is deliberately model-free: inspector and challenger read recorded evidence, the reporter
combines their verdicts. It exercises the multi-agent runtime without pretending that a language
model proved anything.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from openjiuwen.core.multi_agent.config import TeamConfig
from openjiuwen.core.multi_agent.schema.team_card import TeamCard
from openjiuwen.core.multi_agent.team import BaseTeam
from openjiuwen.core.multi_agent.team_runtime import CommunicableAgent
from openjiuwen.core.session.session import Session as AgentSession
from openjiuwen.core.single_agent.base import BaseAgent
from openjiuwen.core.single_agent.schema.agent_card import AgentCard


class _Inspector(CommunicableAgent, BaseAgent):  # type: ignore[misc]
    def configure(self, config: Any) -> _Inspector:
        return self

    async def invoke(self, inputs: Any, session: AgentSession | None = None) -> Any:
        data = inputs if isinstance(inputs, dict) else {}
        checks = {
            "policy_ok": bool(data.get("policy_ok")),
            "verdict_allow": bool(data.get("verdict_allow")),
            "challenge_allow": data.get("challenge_allow") is not False,
            "proof_bound": bool(data.get("proof_sha256")),
            "commit_bound": bool(data.get("commit")),
        }
        return {
            "role": "inspector",
            "allow": all(checks.values()),
            "checks": checks,
        }

    async def stream(self, inputs: Any, session: AgentSession | None = None) -> AsyncIterator[Any]:
        yield await self.invoke(inputs, session)


class _Challenger(CommunicableAgent, BaseAgent):  # type: ignore[misc]
    def configure(self, config: Any) -> _Challenger:
        return self

    async def invoke(self, inputs: Any, session: AgentSession | None = None) -> Any:
        data = inputs if isinstance(inputs, dict) else {}
        risky = str(data.get("risk") or "low") == "high"
        gaps = list(data.get("not_tested") or [])
        return {
            "role": "challenger",
            "allow": not risky and not gaps,
            "high_risk": risky,
            "gaps": gaps,
        }

    async def stream(self, inputs: Any, session: AgentSession | None = None) -> AsyncIterator[Any]:
        yield await self.invoke(inputs, session)


class _Reporter(CommunicableAgent, BaseAgent):  # type: ignore[misc]
    def configure(self, config: Any) -> _Reporter:
        return self

    async def invoke(self, inputs: Any, session: AgentSession | None = None) -> Any:
        data = inputs if isinstance(inputs, dict) else {}
        inspector = data.get("inspector") or {}
        challenger = data.get("challenger") or {}
        allow = bool(inspector.get("allow")) and bool(challenger.get("allow"))
        blockers = []
        for key, passed in (inspector.get("checks") or {}).items():
            if not passed:
                blockers.append(f"inspector: {key}")
        if challenger.get("high_risk"):
            blockers.append("challenger: high risk")
        blockers.extend(f"challenger: not tested: {item}" for item in challenger.get("gaps") or [])
        return {
            "role": "reporter",
            "verdict": "allow" if allow else "block",
            "blockers": blockers,
            "inspector": inspector,
            "challenger": challenger,
        }

    async def stream(self, inputs: Any, session: AgentSession | None = None) -> AsyncIterator[Any]:
        yield await self.invoke(inputs, session)


class VerificationTeam(BaseTeam):  # type: ignore[misc]
    """Three deterministic roles; TeamRuntime owns lifecycle and message passing."""

    def __init__(self) -> None:
        card = TeamCard(
            id="works-verification-team",
            name="works-verification-team",
            description="Inspector + challenger + reporter for a Works proof",
        )
        super().__init__(card=card, config=TeamConfig(max_agents=3))
        self.inspector_card = AgentCard(
            id="inspector", name="inspector", description="checks the recorded evidence"
        )
        self.challenger_card = AgentCard(
            id="challenger", name="challenger", description="looks for residual risk"
        )
        self.reporter_card = AgentCard(
            id="reporter", name="reporter", description="combines the verdict"
        )
        (
            self.add_agent(self.inspector_card, lambda: _Inspector(card=self.inspector_card))
            .add_agent(self.challenger_card, lambda: _Challenger(card=self.challenger_card))
            .add_agent(self.reporter_card, lambda: _Reporter(card=self.reporter_card))
        )

    async def verify(self, payload: dict[str, Any]) -> dict[str, Any]:
        await self.runtime.start()
        try:
            inspected = await self.runtime.send(
                message=payload,
                recipient="inspector",
                sender="main_process",
            )
            challenged = await self.runtime.send(
                message=payload,
                recipient="challenger",
                sender="main_process",
            )
            return cast(
                dict[str, Any],
                await self.runtime.send(
                    message={"inspector": inspected, "challenger": challenged},
                    recipient="reporter",
                    sender="main_process",
                ),
            )
        finally:
            await self.runtime.stop()

    async def invoke(self, message: Any, session: Any = None) -> Any:
        return await self.verify(message if isinstance(message, dict) else {})

    async def stream(self, message: Any, session: Any = None) -> AsyncIterator[Any]:
        yield await self.invoke(message, session)
