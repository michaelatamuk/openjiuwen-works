"""The CLI parser, composed from one registration function per command group."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.interfaces.cli.commands.common import DESCRIPTION
from works.interfaces.cli.parser.daemon import add_daemon_commands
from works.interfaces.cli.parser.delivery import add_delivery_commands
from works.interfaces.cli.parser.inspect import add_inspect_commands
from works.interfaces.cli.parser.intake import add_intake_commands
from works.interfaces.cli.parser.maintenance import add_maintenance_commands
from works.interfaces.cli.parser.memory import add_memory_commands
from works.interfaces.cli.parser.plan import add_plan_commands
from works.interfaces.cli.parser.run import add_run_commands
from works.interfaces.cli.parser.sources import add_sources_commands
from works.interfaces.cli.parser.tasks import add_tasks_commands
from works.interfaces.cli.parser.ui import add_ui_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="works", description=DESCRIPTION)
    parser.add_argument("--home", type=Path, default=None, help="Workspace root")
    sub = parser.add_subparsers(dest="command", required=True)

    add_tasks_commands(sub)
    add_plan_commands(sub)
    add_run_commands(sub)
    add_daemon_commands(sub)
    add_delivery_commands(sub)
    add_intake_commands(sub)
    add_sources_commands(sub)
    add_inspect_commands(sub)
    add_memory_commands(sub)
    add_maintenance_commands(sub)
    add_ui_commands(sub)
    return parser
