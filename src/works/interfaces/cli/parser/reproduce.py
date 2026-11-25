"""`reproduce` command registration."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.interfaces.cli.commands.reproduce import cmd_reproduce


def add_reproduce_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    reproduce = sub.add_parser(
        "reproduce", help="Detect how to check a repository, prepare its env, or resolve a checkout"
    )
    reproduce.add_argument("action", choices=["detect", "prepare", "checkout"])
    reproduce.add_argument("--repo", type=Path, default=None)
    reproduce.add_argument("--url", default=None)
    reproduce.add_argument("--ref", default=None)
    reproduce.add_argument("--hint", default=None)
    reproduce.add_argument("--offline", action="store_true")
    reproduce.add_argument("--json", action="store_true")
    reproduce.set_defaults(func=cmd_reproduce)
