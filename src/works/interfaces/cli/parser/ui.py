"""`ui` command registration."""

from __future__ import annotations

import argparse

from works.interfaces.cli.commands.ui import cmd_ui


def add_ui_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    ui = sub.add_parser("ui", help="Open the local UI")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--read-only", action="store_true", help="Serve reads only (default)")
    ui.add_argument("--write", action="store_true", help="Allow write routes")
    ui.add_argument("--no-open", action="store_true", help="Do not open a browser")
    ui.add_argument("--json", action="store_true")
    ui.set_defaults(func=cmd_ui)
