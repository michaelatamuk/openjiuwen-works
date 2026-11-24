"""`backup` and `restore` registration."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.interfaces.cli.commands.maintenance import cmd_backup, cmd_restore


def add_maintenance_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    backup = sub.add_parser("backup", help="Archive queue, runs, ledger, flows and settings")
    backup.add_argument("--out", type=Path, required=True)
    backup.add_argument("--json", action="store_true")
    backup.set_defaults(func=cmd_backup)

    restore = sub.add_parser("restore", help="Restore a backup into the current home")
    restore.add_argument("--from", dest="source", type=Path, required=True)
    restore.add_argument("--force", action="store_true", help="Replace existing queue/runs/flows")
    restore.add_argument("--json", action="store_true")
    restore.set_defaults(func=cmd_restore)
