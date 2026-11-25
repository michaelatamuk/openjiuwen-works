"""Read-only checks that a plan can actually run: commands exist, scripts exist.

Nothing is executed here. A missing executable is a plan error; a file that does not exist yet is a
warning, because a plan may legitimately create it.
"""

from __future__ import annotations

import shlex
import shutil
import sys
from pathlib import Path

from works.application.planning.context import PlannerContext
from works.domain.plan import PlanProposal


def _executable(command: str) -> str | None:
    if command.strip().startswith("{python}"):
        return sys.executable
    try:
        argv = shlex.split(command, posix=sys.platform != "win32")
    except ValueError:
        return None
    if not argv:
        return None
    binary = argv[0].strip("\"'")
    if Path(binary).is_absolute() or "/" in binary or "\\" in binary:
        return binary if Path(binary).exists() else None
    return binary if shutil.which(binary) else None


def problems(proposal: PlanProposal, context: PlannerContext) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for step in proposal.steps:
        label = step.id or step.node
        for command in step.commands:
            if _executable(command) is None:
                errors.append(f"step {label!r} runs a command that is not available: {command!r}")
        for path in step.files:
            if not (context.repo / path).exists():
                warnings.append(f"step {label!r} names {path!r}, which does not exist yet")
    base = context.scenario_set.parent
    for scenario in context.scenarios.scenarios:
        script = base / context.scenarios.directory / scenario.script
        if not script.exists():
            errors.append(
                f"scenario {scenario.id!r} points at a missing script: {scenario.script!r}"
            )
    return errors, warnings
