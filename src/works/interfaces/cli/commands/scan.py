"""`works scan` — run a check, keep a baseline, file only new failures."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.adapters.processes.runner import SubprocessRunner
from works.application.scan import scan_repository
from works.domain.errors import ConfigError
from works.interfaces.cli.commands.common import _emit, _paths


def cmd_scan(args: argparse.Namespace) -> int:
    paths = _paths(args)
    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        raise ConfigError(f"not a repository: {repo}")
    try:
        result = scan_repository(
            paths,
            repo,
            args.command,
            runner=SubprocessRunner(),
            product=args.product,
            timeout_s=args.timeout_s,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError) as exc:
        raise ConfigError(f"scan failed: {exc}") from exc
    if args.json:
        _emit(
            {
                "command": result.command,
                "exit_code": result.exit_code,
                "failures": result.failures,
                "new": result.new,
                "fixed": result.fixed,
                "created": result.created,
                "existing": result.existing,
                "baseline_written": result.baseline_written,
            }
        )
        return 0
    print(
        f"scan: exit {result.exit_code} · {len(result.failures)} failure(s) · "
        f"{len(result.new)} new · {len(result.fixed)} fixed"
    )
    for failure in result.new:
        print(f"new: {failure}")
    for failure in result.fixed:
        print(f"fixed: {failure}")
    if result.created:
        print(f"created: {', '.join(result.created)}")
    if result.existing:
        print(f"already queued: {', '.join(result.existing)}")
    print("baseline updated" if result.baseline_written else "dry run: baseline unchanged")
    return 0
