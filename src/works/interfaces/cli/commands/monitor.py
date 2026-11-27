"""`works monitor` — re-check released changes and file a task on drift."""

from __future__ import annotations

import argparse
from dataclasses import asdict

from works.application.monitor import monitor
from works.interfaces.cli.commands.common import _emit, _paths


def cmd_monitor(args: argparse.Namespace) -> int:
    result = monitor(_paths(args), days=args.days, dry_run=args.dry_run)
    if args.json:
        _emit(
            {
                "days": result.days,
                "checked": result.checked,
                "skipped": result.skipped,
                "checks": [asdict(item) for item in result.checks],
                "created": result.created,
                "existing": result.existing,
            }
        )
        return 0
    print(f"monitor · last {result.days} days · checked {result.checked}")
    for item in result.checks:
        state = "drift" if item.drifted else "hold"
        print(
            f"{state}: {item.task_id} · {item.target or 'unknown target'} · "
            f"{'pass' if item.baseline_ok else 'fail'} -> {'pass' if item.now_ok else 'fail'}"
            + (f" · {item.code}" if item.code else "")
        )
        if item.created:
            print(f"  created: {item.created}")
        if item.existing:
            print(f"  already queued: {item.existing}")
    for task_id, reason in result.skipped.items():
        print(f"skipped: {task_id} · {reason}")
    if args.dry_run:
        print("dry run: no task and no state was written")
    return 0
