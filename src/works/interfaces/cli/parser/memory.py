"""`memory` command registration."""

from __future__ import annotations

import argparse

from works.interfaces.cli.commands.memory import (
    cmd_memory_backfill,
    cmd_memory_recall,
)


def add_memory_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    memory = sub.add_parser("memory", help="PPMA memory tools")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    backfill = memory_sub.add_parser("backfill", help="Report already-finished runs to PPMA")
    backfill.add_argument("--ppma", default=None, help="PPMA base URL")
    backfill.add_argument("--space", default="me")
    backfill.add_argument("--limit", type=int, default=None)
    backfill.add_argument("--task", default=None)
    backfill.add_argument("--since", default=None)
    backfill.add_argument("--dry-run", action="store_true")
    backfill.add_argument("--json", action="store_true")
    backfill.set_defaults(func=cmd_memory_backfill)
    recall = memory_sub.add_parser("recall", help="Read PPMA memory statements")
    recall.add_argument("--ppma", default=None, help="PPMA base URL")
    recall.add_argument("--space", default="me")
    recall.add_argument("--view", default="about_me")
    recall.add_argument("--limit", type=int, default=8)
    recall.add_argument("--json", action="store_true")
    recall.set_defaults(func=cmd_memory_recall)
