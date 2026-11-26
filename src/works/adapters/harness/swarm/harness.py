"""An isolated harness boundary for JiuwenSwarm.

JiuwenSwarm is a full multi-agent platform: its own runtime, gateway, A2A server, tool approvals
and a pinned `openjiuwen` commit. It is not a library that takes `(repo) -> patch` in one call, and
its CLI does not belong in Works' virtualenv.

So Works talks to it the same way it would talk to any external builder: a separate process with a
small, explicit JSON contract and a filesystem-only view of the worktree.

    request file  ->  external entrypoint  ->  result file

The entrypoint is a program (or a small adapter around JiuwenSwarm's A2A/CLI) that reads
`--works-request PATH` and writes `--works-result PATH`. `works swarm doctor` checks whether such
an entrypoint can start; a missing or broken platform is reported, never replaced by a fake build.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from works.adapters.harness.base import Proposal, ProposalRequest
from works.adapters.harness.swarm.contract import (
    CONTRACT,
    SwarmChallenge,
    SwarmDiagnostic,
    SwarmProposal,
    SwarmRequest,
)
from works.adapters.harness.swarm.runtime import (
    _tail,
    default_entrypoint,
    default_swarm_home,
    default_swarm_python,
    preflight,
    status,
)
from works.adapters.processes.runner import CommandRunner, SubprocessRunner
from works.domain.errors import HarnessError
from works.domain.records import Challenge

__all__ = [
    "CONTRACT",
    "SwarmChallenge",
    "SwarmDiagnostic",
    "SwarmHarness",
    "SwarmProposal",
    "SwarmRequest",
    "default_entrypoint",
    "default_swarm_home",
    "default_swarm_python",
    "preflight",
    "status",
]


@dataclass
class SwarmHarness:
    """Run an external builder with the `works.swarm.v1` contract.

    `runner` is injectable so the contract can be tested without JiuwenSwarm installed. The default
    entrypoint is deliberately the real CLI: a broken platform fails loudly at preflight.
    """

    python: Path = field(default_factory=default_swarm_python)
    home: Path = field(default_factory=default_swarm_home)
    entrypoint: list[str] = field(default_factory=default_entrypoint)
    runner: CommandRunner = field(default_factory=SubprocessRunner)
    timeout_s: int = 1800
    env: dict[str, str] = field(default_factory=dict)
    name: str = "jiuwenswarm"
    supports_reviews: bool = False

    def diagnostic(self) -> SwarmDiagnostic:
        return preflight(
            self.python, entrypoint=self.entrypoint, home=self.home, runner=self.runner
        )

    async def _invoke(self, request: ProposalRequest, kind: str) -> dict[str, Any]:
        diagnostic = self.diagnostic()
        if not diagnostic.ok:
            raise HarnessError(f"JiuwenSwarm is not ready: {diagnostic.detail}")
        payload = SwarmRequest(
            task_id=request.task_id,
            source_ref=request.source_ref,
            title=request.title,
            worktree=str(request.worktree),
            base_commit=request.base_commit,
            plan=request.plan,
        ).model_dump(mode="json")
        with tempfile.TemporaryDirectory(prefix="works-swarm-") as directory:
            root = Path(directory)
            request_path = root / "request.json"
            result_path = root / "result.json"
            request_path.write_text(json.dumps(payload), encoding="utf-8")
            merged = {
                "PYTHONPATH": os.pathsep.join(
                    [str(self.home), os.environ.get("PYTHONPATH", "")]
                ).strip(os.pathsep),
                **self.env,
            }
            result = await asyncio.to_thread(
                self.runner.run,
                [
                    str(self.python),
                    *self.entrypoint,
                    "--works-kind",
                    kind,
                    "--works-request",
                    str(request_path),
                    "--works-result",
                    str(result_path),
                ],
                request.worktree,
                env=merged,
                timeout_s=self.timeout_s,
            )
            if not result.ok or not result_path.exists():
                raise HarnessError(
                    f"JiuwenSwarm produced no result: exit {result.exit_code}; {_tail(result)}"
                )
            try:
                parsed: Any = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise HarnessError(f"JiuwenSwarm returned invalid JSON: {exc}") from exc
            if not isinstance(parsed, dict):
                raise HarnessError("JiuwenSwarm returned a non-object result")
            return parsed

    async def propose(self, request: ProposalRequest) -> Proposal:
        parsed = await self._invoke(request, "propose")
        try:
            proposal = SwarmProposal.model_validate(parsed)
        except ValidationError as exc:
            raise HarnessError(f"JiuwenSwarm proposal is invalid: {exc}") from exc
        return Proposal(
            patch=proposal.patch,
            applied=proposal.applied,
            touched_paths=proposal.touched_paths,
            trace=proposal.trace,
            model=proposal.model,
            provider=proposal.provider,
            tokens=proposal.tokens,
            usd=proposal.usd,
            notes=proposal.notes,
            stop=proposal.stop,
        )

    async def challenge(self, request: ProposalRequest, proposal: Proposal) -> Challenge:
        parsed = await self._invoke(request, "challenge")
        try:
            challenge = SwarmChallenge.model_validate(parsed)
        except ValidationError as exc:
            raise HarnessError(f"JiuwenSwarm challenge is invalid: {exc}") from exc
        return Challenge(
            allow=challenge.allow,
            reason=challenge.reason,
            concerns=challenge.concerns,
            model=challenge.model,
            provider=challenge.provider,
            tokens=challenge.tokens,
            usd=challenge.usd,
        )
