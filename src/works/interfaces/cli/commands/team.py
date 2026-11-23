"""CLI command group."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from works.domain.errors import (
    EXIT_BLOCKED,
)
from works.interfaces.cli.commands.common import _emit, _paths

if TYPE_CHECKING:
    pass


def cmd_team_verify(args: argparse.Namespace) -> int:
    from works.application.team.launcher import run_team_verify

    result = run_team_verify(_paths(args), args.task_id)
    if args.json:
        _emit(result)
    else:
        print(f"team verdict: {result.get('verdict')}")
        for blocker in result.get("blockers") or []:
            print(f"  blocker: {blocker}")
    return 0 if result.get("verdict") == "allow" else EXIT_BLOCKED
