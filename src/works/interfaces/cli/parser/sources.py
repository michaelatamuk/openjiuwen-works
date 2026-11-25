"""`sources` command registration."""

from __future__ import annotations

import argparse

from works.interfaces.cli.commands.sources import cmd_sources


def add_sources_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    sources = sub.add_parser("sources", help="List, enable or disable webhook sources")
    sources.add_argument("action", choices=["list", "enable", "disable"], nargs="?", default="list")
    sources.add_argument("name", nargs="?", help="source name for enable/disable")
    sources.add_argument("--json", action="store_true")
    sources.set_defaults(func=cmd_sources)
