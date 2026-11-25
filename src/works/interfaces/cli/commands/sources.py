"""`works sources` — inspect and toggle webhook sources."""

from __future__ import annotations

import argparse
import os
from typing import Any

from works.application import webhooks
from works.interfaces.cli.commands.common import _emit, _paths


def _rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    paths = _paths(args)
    metrics = webhooks.read_metrics(paths)
    rows: list[dict[str, Any]] = []
    for name, config in webhooks.load_registry(paths).items():
        rows.append(
            {
                "name": name,
                "enabled": config.enabled,
                "product": config.product,
                "repo": config.repo,
                "limit_per_minute": config.limit_per_minute,
                "secret_env": config.secret_env,
                "secret_set": bool(os.environ.get(config.secret_env)),
                "metrics": metrics.get(name, {}),
            }
        )
    return rows


def cmd_sources(args: argparse.Namespace) -> int:
    paths = _paths(args)
    if args.action in ("enable", "disable"):
        entries = webhooks.load_registry(paths)
        config = entries.get(args.name)
        if config is None:
            raise SystemExit(f"unknown source {args.name!r}")
        config.enabled = args.action == "enable"
        webhooks.save_registry(paths, entries)
        if args.json:
            _emit({"source": config.model_dump()})
        else:
            state = "enabled" if config.enabled else "disabled"
            print(f"{config.name}: {state}")
        return 0
    rows = _rows(args)
    if args.json:
        _emit({"sources": rows})
        return 0
    from works.interfaces.cli.render import table

    print(
        table(
            ("source", "enabled", "product", "secret", "accepted", "duplicates", "rejected"),
            [
                (
                    row["name"],
                    "yes" if row["enabled"] else "no",
                    row["product"],
                    "set" if row["secret_set"] else "missing",
                    (row["metrics"] or {}).get("accepted", 0),
                    (row["metrics"] or {}).get("duplicates", 0),
                    (row["metrics"] or {}).get("rejected", 0),
                )
                for row in rows
            ],
        )
    )
    return 0
