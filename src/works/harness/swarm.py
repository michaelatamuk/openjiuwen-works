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

from pydantic import BaseModel, Field, ValidationError

from ..errors import ConfigError, HarnessError
from ..records import Challenge
from ..runner import CommandResult, CommandRunner, SubprocessRunner
from .base import Proposal, ProposalRequest

CONTRACT = "works.swarm.v1"


class SwarmRequest(BaseModel):
    contract: str = CONTRACT
    task_id: str
    source_ref: str
    title: str
    worktree: str
    base_commit: str


class SwarmProposal(BaseModel):
    """What the external builder must return. Only `patch` is required."""

    patch: str = ""
    applied: bool = False
    touched_paths: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    model: str = "jiuwenswarm"
    provider: str = "jiuwenswarm"
    tokens: int = Field(default=0, ge=0)
    usd: float = Field(default=0.0, ge=0)
    notes: list[str] = Field(default_factory=list)
    stop: str | None = None


class SwarmChallenge(BaseModel):
    allow: bool
    reason: str = ""
    concerns: list[str] = Field(default_factory=list)
    model: str = "jiuwenswarm"
    provider: str = "jiuwenswarm"
    tokens: int = Field(default=0, ge=0)
    usd: float = Field(default=0.0, ge=0)


@dataclass(frozen=True)
class SwarmDiagnostic:
    ok: bool
    detail: str
    argv: tuple[str, ...] = ()
    exit_code: int | None = None
    output_tail: str = ""


def default_swarm_python() -> Path:
    return Path(
        os.environ.get("WORKS_SWARM_PYTHON")
        or r"C:\Workspace\openjiuwen\jiuwenswarm\.venv\Scripts\python.exe"
    )


def default_swarm_home() -> Path:
    return Path(os.environ.get("WORKS_SWARM_HOME") or r"C:\Workspace\openjiuwen\jiuwenswarm")


def default_entrypoint() -> list[str]:
    raw = os.environ.get("WORKS_SWARM_ENTRYPOINT")
    if not raw:
        return ["-m", "jiuwenswarm.channels.cli", "--help"]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError("WORKS_SWARM_ENTRYPOINT must be a JSON array of arguments") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ConfigError("WORKS_SWARM_ENTRYPOINT must be a JSON array of strings")
    return parsed


def preflight(
    python: Path | None = None,
    *,
    entrypoint: list[str] | None = None,
    home: Path | None = None,
    runner: CommandRunner | None = None,
    timeout_s: int = 60,
) -> SwarmDiagnostic:
    interpreter = python or default_swarm_python()
    checkout = home or default_swarm_home()
    if not interpreter.exists():
        return SwarmDiagnostic(
            ok=False,
            detail=f"JiuwenSwarm interpreter not found: {interpreter}",
            argv=(str(interpreter),),
        )
    if not checkout.exists():
        return SwarmDiagnostic(
            ok=False,
            detail=f"JiuwenSwarm checkout not found: {checkout}",
            argv=(str(interpreter),),
        )
    resolved_entrypoint = entrypoint or default_entrypoint()
    argv = [str(interpreter), *resolved_entrypoint]
    if not any(flag in resolved_entrypoint for flag in ("-m", "--help")):
        return SwarmDiagnostic(
            ok=True,
            detail="entrypoint configured; it is probed on the first real run",
            argv=tuple(argv),
        )
    if "-m" in resolved_entrypoint and "--help" not in resolved_entrypoint:
        argv.append("--help")
    result = (runner or SubprocessRunner()).run(
        argv,
        checkout,
        env={"PYTHONPATH": str(checkout)},
        timeout_s=timeout_s,
    )
    tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-6:])
    if result.ok:
        return SwarmDiagnostic(
            ok=True, detail="entrypoint started", argv=tuple(argv), exit_code=0, output_tail=tail
        )
    return SwarmDiagnostic(
        ok=False,
        detail=_diagnose(tail),
        argv=tuple(argv),
        exit_code=result.exit_code,
        output_tail=tail,
    )


def _diagnose(tail: str) -> str:
    if "agent_gateway" in tail:
        return (
            "the JiuwenSwarm CLI imports `agent_gateway`, which is not on its path; "
            "install the gateway package or use the Docker image, then point "
            "WORKS_SWARM_ENTRYPOINT at an adapter that implements the works.swarm.v1 contract"
        )
    if "ModuleNotFoundError" in tail:
        return "the JiuwenSwarm entrypoint has missing dependencies; use its own venv or image"
    return "the JiuwenSwarm entrypoint exited non-zero; see output_tail"


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


def _tail(result: CommandResult) -> str:
    lines = (result.stderr or result.stdout).strip().splitlines()
    return lines[-1] if lines else "no output"
