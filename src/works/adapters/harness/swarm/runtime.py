"""Locate the JiuwenSwarm entrypoint and probe it."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from works.adapters.harness.swarm.contract import CONTRACT, SwarmDiagnostic
from works.adapters.processes.runner import CommandResult, CommandRunner, SubprocessRunner
from works.config.resources import worker
from works.domain.errors import ConfigError


def default_swarm_python() -> Path:
    return Path(
        os.environ.get("WORKS_SWARM_PYTHON")
        or r"C:\Workspace\openjiuwen\jiuwenswarm\.venv\Scripts\python.exe"
    )


def default_swarm_home() -> Path:
    return Path(os.environ.get("WORKS_SWARM_HOME") or r"C:\Workspace\openjiuwen\jiuwenswarm")


def _repo_adapter() -> Path | None:
    adapter = worker("swarm_adapter.py")
    return adapter if adapter is not None and adapter.is_file() else None


def default_entrypoint() -> list[str]:
    raw = os.environ.get("WORKS_SWARM_ENTRYPOINT")
    if not raw:
        adapter = _repo_adapter()
        if adapter is not None:
            return [str(adapter)]
        return ["-m", "jiuwenswarm.channels.cli.main", "--help"]
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
    is_script = bool(resolved_entrypoint) and resolved_entrypoint[0].lower().endswith(".py")
    if not is_script and not any(flag in resolved_entrypoint for flag in ("-m", "--help")):
        return SwarmDiagnostic(
            ok=True,
            detail="entrypoint configured; it is probed on the first real run",
            argv=tuple(argv),
        )
    if "--help" not in resolved_entrypoint:
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


def status(
    python: Path | None = None,
    *,
    home: Path | None = None,
) -> dict[str, Any]:
    """Cheap readiness for the Settings panel: no subprocess, no model call.

    A real run still probes the entrypoint (`preflight`); this only answers whether the checkout
    and adapter are present, so the UI can label the runtime without starting a process on every
    poll.
    """
    interpreter = python or default_swarm_python()
    checkout = home or default_swarm_home()
    if not interpreter.exists():
        return {
            "available": False,
            "detail": "JiuwenSwarm interpreter not found.",
            "contract": CONTRACT,
            "docs": "docs/guides/integrations/swarm.md",
            "steps": [
                "Install JiuwenSwarm and create its virtualenv.",
                "Point Works at that interpreter (see docs/guides/integrations/swarm.md).",
                "Run `works swarm doctor` to re-check.",
            ],
        }
    if not checkout.exists():
        return {
            "available": False,
            "detail": "JiuwenSwarm checkout not found.",
            "contract": CONTRACT,
            "docs": "docs/guides/integrations/swarm.md",
            "steps": [
                "Check out the JiuwenSwarm repository.",
                "Point Works at the checkout (see docs/guides/integrations/swarm.md).",
                "Run `works swarm doctor` to re-check.",
            ],
        }
    try:
        entrypoint = default_entrypoint()
    except ConfigError as exc:
        return {
            "available": False,
            "detail": str(exc),
            "contract": CONTRACT,
            "docs": "docs/guides/integrations/swarm.md",
            "steps": ["Fix the works.swarm.v1 entrypoint.", "Run `works swarm doctor`."],
        }
    first = entrypoint[0] if entrypoint else ""
    if first.lower().endswith(".py") and not Path(first).is_file():
        return {
            "available": False,
            "detail": "The works.swarm.v1 adapter is missing.",
            "contract": CONTRACT,
            "docs": "docs/guides/integrations/swarm.md",
            "steps": [
                "Restore scripts/swarm_adapter.py from the repository.",
                "Run `works swarm doctor` to re-check.",
            ],
        }
    return {
        "available": True,
        "detail": "JiuwenSwarm checkout and adapter found; a run probes the entrypoint.",
        "contract": CONTRACT,
        "docs": "docs/guides/integrations/swarm.md",
        "steps": [
            "Ready. A run probes the adapter before it starts.",
            "Models, gateway and credentials are configured inside JiuwenSwarm.",
        ],
    }


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


def _tail(result: CommandResult) -> str:
    lines = (result.stderr or result.stdout).strip().splitlines()
    return lines[-1] if lines else "no output"
