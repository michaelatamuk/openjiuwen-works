"""`daemon` command registration."""

from __future__ import annotations

import argparse

from works.interfaces.cli.commands.daemon import cmd_daemon


def add_daemon_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    daemon = sub.add_parser("daemon", help="Run the local API daemon")
    daemon.add_argument("--host", default="127.0.0.1")
    daemon.add_argument("--port", type=int, default=8765)
    daemon.add_argument("--write", action="store_true", help="Allow write routes")
    daemon.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow a non-loopback bind (not recommended)",
    )
    daemon.set_defaults(func=cmd_daemon)
