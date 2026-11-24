"""CLI command group."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from works.interfaces.cli.commands.common import _emit, _paths, _queue
from works.interfaces.cli.render import table


def cmd_metrics(args: argparse.Namespace) -> int:
    from works.adapters.queue.ledger import Ledger
    from works.application.observability.escapes import read_report
    from works.application.observability.metrics import collect

    metrics = collect(
        _queue(args),
        Ledger(_paths(args).ledger),
        escape_report=read_report(_paths(args)),
    )
    if args.json:
        _emit({"metrics": metrics.model_dump(mode="json")})
        return 0
    print(
        table(
            ("metric", "value"),
            [
                ("tasks", metrics.tasks),
                ("proved", metrics.proved),
                ("blocked", metrics.blocked),
                ("human touches", metrics.human_touches),
                ("runs without human", metrics.runs_without_human),
                ("waiting (ms)", metrics.waiting_ms),
                ("median duration (ms)", metrics.median_duration_ms or "-"),
                ("tokens", metrics.tokens),
                ("usd", f"{metrics.usd:.4f}"),
                ("escapes", metrics.escapes),
                ("rework", metrics.rework),
            ],
        )
    )
    if metrics.per_task:
        print()
        print(
            table(
                ("task", "state", "ms", "touches", "waiting ms", "tokens", "usd"),
                [
                    (
                        item.task_id,
                        item.state.value,
                        item.duration_ms,
                        item.human_touches,
                        item.waiting_ms,
                        item.tokens,
                        f"{item.usd:.4f}",
                    )
                    for item in metrics.per_task
                ],
            )
        )
    return 0


def cmd_escapes(args: argparse.Namespace) -> int:
    from works.application.observability.escapes import append_events, scan, write_report

    report = scan(_paths(args), days=args.days)
    if not args.dry_run:
        write_report(_paths(args), report)
        append_events(_paths(args), report)
    if args.json:
        _emit(
            {
                "escapes": report.as_dict(),
                "written": not args.dry_run,
            }
        )
        return 0
    print(
        table(
            ("metric", "value"),
            [
                ("window (days)", report.window_days),
                ("escapes", report.escapes),
                ("rework", len(report.rework)),
            ],
        )
    )
    for finding in report.findings:
        print(f"  {finding.kind.value}: {finding.task_id} at {finding.evidence_commit[:12]}")
    for rework in report.rework:
        print(f"  rework: {rework.task_id} repeats {rework.previous_task_id}")
    return 0


def cmd_ledger(args: argparse.Namespace) -> int:
    from works.adapters.queue.ledger import Ledger

    rows = Ledger(_paths(args).ledger).rows()
    if args.json:
        _emit({"rows": [row.model_dump(mode="json") for row in rows]})
        return 0
    rendered = [
        (
            row.ts.isoformat(timespec="seconds"),
            row.task_id,
            row.run_id or "-",
            row.state.value,
            row.verdict or "-",
            row.tokens if row.tokens is not None else "-",
            f"{row.usd:.4f}" if row.usd is not None else "-",
        )
        for row in rows
    ]
    print(table(("ts", "task", "run", "state", "verdict", "tokens", "usd"), rendered))
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    from works.application.schema import all_schemas

    payload = all_schemas()
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print(f"Schemas (v{payload['schema_version']})")
    for name, model_schema in payload["schemas"].items():
        print(f"  {name}: {model_schema.get('title', '')}")
    print("Use `works schema --json` for the full documents.")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from works.application.doctor import failed, run_checks

    paths = _paths(args)
    repo = (args.repo or Path.cwd()).expanduser().resolve()
    results = run_checks(paths, repo=repo)
    if args.json:
        _emit({"checks": [result.model_dump() for result in results]})
    else:
        print(
            table(
                ("check", "status", "detail"),
                [(result.name, result.status, result.detail) for result in results],
            )
        )
    return 1 if failed(results) else 0
