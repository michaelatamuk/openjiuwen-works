"""CLI command group."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import TYPE_CHECKING

from works.domain.errors import (
    EXIT_INTERNAL,
    ConfigError,
)
from works.interfaces.cli.commands.common import _emit, _paths

if TYPE_CHECKING:
    pass


def cmd_memory_backfill(args: argparse.Namespace) -> int:
    from datetime import UTC, datetime

    from works.application.memory.backfill import backfill_runs
    from works.application.memory.ppma import NullMemory, PpmaMemory

    url = args.ppma or os.environ.get("WORKS_PPMA_URL")
    if not url and not args.dry_run:
        raise ConfigError("PPMA url is required; pass --ppma or set WORKS_PPMA_URL")
    since = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ConfigError(f"invalid --since value {args.since!r}") from exc
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)
    memory = NullMemory() if args.dry_run else PpmaMemory(url or "", space=args.space)
    entries = backfill_runs(
        _paths(args),
        memory,
        limit=args.limit,
        dry_run=args.dry_run,
        task_id=args.task,
        since=since,
    )
    counts = {
        status: sum(1 for entry in entries if entry.status == status)
        for status in ("reported", "skipped", "failed")
    }
    payload = {
        "url": url,
        "dry_run": args.dry_run,
        "reported": counts["reported"],
        "skipped": counts["skipped"],
        "failed": counts["failed"],
        "runs": [entry.as_dict() for entry in entries],
    }
    if args.json:
        print(
            json.dumps(
                {"ok": counts["failed"] == 0, **payload},
                ensure_ascii=False,
                default=str,
                separators=(",", ":"),
            )
        )
    elif args.dry_run:
        print(f"PPMA backfill dry run: {len(entries)} readable run(s); nothing was sent.")
    else:
        print(
            f"PPMA backfill: {counts['reported']} reported, "
            f"{counts['skipped']} skipped, {counts['failed']} failed."
        )
        for entry in entries:
            if entry.status == "failed":
                print(f"  {entry.run_id}: {entry.error}", file=sys.stderr)
    return EXIT_INTERNAL if counts["failed"] else 0


def cmd_memory_recall(args: argparse.Namespace) -> int:
    from works.application.memory.ppma import PpmaMemory

    url = args.ppma or os.environ.get("WORKS_PPMA_URL")
    if not url:
        raise ConfigError("PPMA url is required; pass --ppma or set WORKS_PPMA_URL")
    memory = PpmaMemory(url, space=args.space)
    try:
        statements = memory.recall(view=args.view, limit=args.limit)
    except RuntimeError as exc:
        raise ConfigError(str(exc)) from exc
    if args.json:
        _emit({"view": args.view, "statements": statements})
    elif not statements:
        print("No memory statements.")
    else:
        for statement in statements:
            print(f"- {statement}")
    return 0
