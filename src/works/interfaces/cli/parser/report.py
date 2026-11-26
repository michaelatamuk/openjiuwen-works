"""`report` command registration."""

from __future__ import annotations

import argparse

from works.interfaces.cli.commands.report import cmd_report


def add_report_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    report = sub.add_parser("report", help="Summarise time, cost and gate decisions")
    report.add_argument("--days", type=int, default=30, help="Window in days (default 30)")
    report.add_argument("--json", action="store_true")
    report.set_defaults(func=cmd_report)
