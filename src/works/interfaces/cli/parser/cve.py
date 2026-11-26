"""`cve` command registration."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.interfaces.cli.commands.cve import cmd_cve


def add_cve_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    cve = sub.add_parser("cve", help="Scan a repository's lockfiles for advisories")
    actions = cve.add_subparsers(dest="cve_command", required=True)
    scan = actions.add_parser("scan", help="Match pinned packages against a feed")
    scan.add_argument("--repo", required=True, type=Path, help="Repository to read")
    scan.add_argument("--feed", type=Path, default=None, help="Offline OSV-style JSON feed")
    scan.add_argument("--osv", action="store_true", help="Query api.osv.dev instead of a feed")
    scan.add_argument("--product", default="openjiuwen")
    scan.add_argument("--json", action="store_true")
    scan.set_defaults(func=cmd_cve)
