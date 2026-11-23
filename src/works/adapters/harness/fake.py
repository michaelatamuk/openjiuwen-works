"""A fake harness that replays a recorded trace. Used by M0.5 and by CI."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from works.adapters.harness.base import Proposal, ProposalRequest
from works.domain.errors import HarnessError
from works.domain.records import Challenge


class Trace(BaseModel):
    schema_version: int = 1
    name: str
    model: str = "fake-builder-1"
    provider: str = "fixture"
    tokens: int = 0
    usd: float = 0.0
    stop: str | None = None
    patch_file: str | None = None
    patch: str | None = None
    notes: list[str] = Field(default_factory=list)
    delay_s: float = 0.0
    challenge_allow: bool = True
    challenge_reason: str = "fixture challenge passed"
    challenge_concerns: list[str] = Field(default_factory=list)


class FakeHarness:
    """Deterministic by construction: same trace, same proposal, no live call."""

    name = "fake"

    def __init__(self, trace_path: Path) -> None:
        self._trace_path = trace_path
        self._trace = self._load(trace_path)

    @staticmethod
    def _load(path: Path) -> Trace:
        if not path.exists():
            raise HarnessError(f"trace not found: {path}")
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HarnessError(f"{path} is not valid JSON: {exc}") from exc
        try:
            return Trace.model_validate(raw)
        except ValidationError as exc:
            raise HarnessError(f"{path} is not a valid trace: {exc}") from exc

    def proposal(self) -> Proposal:
        trace = self._trace
        patch = ""
        if trace.patch is not None:
            patch = trace.patch
        elif trace.patch_file is not None:
            patch_path = (self._trace_path.parent / trace.patch_file).resolve()
            if not patch_path.exists():
                raise HarnessError(f"patch file not found: {patch_path}")
            patch = patch_path.read_text(encoding="utf-8")
        return Proposal(
            patch=patch,
            model=trace.model,
            provider=trace.provider,
            tokens=trace.tokens,
            usd=trace.usd,
            notes=list(trace.notes),
            stop=trace.stop,
        )

    async def propose(self, request: ProposalRequest) -> Proposal:
        if self._trace.delay_s:
            await asyncio.sleep(self._trace.delay_s)
        else:
            await asyncio.sleep(0)
        proposal = self.proposal()
        if proposal.stop:
            return proposal
        if not proposal.patch.strip():
            raise HarnessError(f"trace {self._trace.name!r} carries no patch and no stop reason")
        return proposal

    async def challenge(self, request: ProposalRequest, proposal: Proposal) -> Challenge:
        await asyncio.sleep(0)
        return Challenge(
            allow=self._trace.challenge_allow,
            reason=self._trace.challenge_reason,
            concerns=list(self._trace.challenge_concerns),
            model=self._trace.model,
            provider=self._trace.provider,
            tokens=0,
            usd=0.0,
        )
