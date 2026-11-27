"""`monitor` command registration."""

from __future__ import annotations

import argparse

from works.interfaces.cli.commands.monitor import cmd_monitor


def add_monitor_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    monitor = sub.add_parser("monitor", help="Re-check released changes and file drift tasks")
    monitor.add_argument("--days", type=int, default=30)
    monitor.add_argument("--dry-run", action="store_true")
    monitor.add_argument("--json", action="store_true")
    monitor.set_defaults(func=cmd_monitor)
