"""`scan` command registration."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.interfaces.cli.commands.scan import cmd_scan


def add_scan_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    scan = sub.add_parser("scan", help="Run a check and file only new failures")
    scan.add_argument("--repo", required=True, type=Path, help="Repository to scan")
    scan.add_argument(
        "--command",
        required=True,
        help='Check command, e.g. "{python} -m pytest -q"',
    )
    scan.add_argument("--product", default="openjiuwen")
    scan.add_argument("--timeout-s", type=int, default=600)
    scan.add_argument(
        "--dry-run", action="store_true", help="Do not create tasks or update baseline"
    )
    scan.add_argument("--json", action="store_true")
    scan.set_defaults(func=cmd_scan)
