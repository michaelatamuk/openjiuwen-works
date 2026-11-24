"""`daemon` command registration."""

from __future__ import annotations

import argparse

from works.interfaces.cli.commands.daemon import cmd_daemon


def add_daemon_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    daemon = sub.add_parser(
        "daemon",
        help="Run or control the local API daemon",
        description=(
            "Run the daemon in the foreground, or use start/stop/status to manage a "
            "detached one. A writable daemon owns the home while it runs."
        ),
    )
    daemon.add_argument(
        "action",
        nargs="?",
        choices=("run", "start", "stop", "status", "pair"),
        default="run",
        help="run in the foreground, or start/stop/status/pair a detached daemon",
    )
    daemon.add_argument("--host", default="127.0.0.1")
    daemon.add_argument("--port", type=int, default=8765)
    daemon.add_argument("--write", action="store_true", help="Allow write routes")
    daemon.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow a non-loopback bind (not recommended)",
    )
    daemon.add_argument(
        "--trusted-host",
        action="append",
        default=None,
        help="Host header allowed on a remote bind; repeat for several names",
    )
    daemon.add_argument("--json", action="store_true")
    daemon.add_argument(
        "--label",
        default="device",
        help="Device label used by `daemon pair`",
    )
    daemon.set_defaults(func=cmd_daemon)
