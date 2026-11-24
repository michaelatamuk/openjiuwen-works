"""CLI command group."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from works.domain.errors import (
    EXIT_POLICY,
    ConfigError,
)
from works.interfaces.cli.commands.common import _emit, _paths, _queue
from works.interfaces.cli.render import table


def cmd_policy_check(args: argparse.Namespace) -> int:
    from works.domain.flow import PathsSpec, find_flow, load_flow
    from works.domain.policy import check_paths

    spec = PathsSpec()
    if args.flow is not None:
        spec = load_flow(find_flow(_paths(args).flows, args.flow)).paths
    violations = check_paths(args.paths, spec)
    if args.json:
        _emit(
            {
                "allowed": not violations,
                "violations": [violation.model_dump() for violation in violations],
            }
        )
    elif violations:
        for violation in violations:
            print(f"{violation.path}: {violation.reason}", file=sys.stderr)
    else:
        print(f"{len(args.paths)} path(s) allowed")
    return EXIT_POLICY if violations else 0


def cmd_risk(args: argparse.Namespace) -> int:
    from works.domain.risk import RiskRating

    events = _queue(args).events(args.task_id)
    ratings = [
        RiskRating.model_validate(event.data) for event in events if event.type == "risk.rated"
    ]
    if not ratings:
        raise ConfigError(f"task {args.task_id} has no risk rating yet")
    latest = ratings[-1]
    if args.json:
        _emit({"risk": latest.model_dump(mode="json")})
        return 0
    print(f"{latest.level.value}: {latest.files} file(s), {latest.lines} line(s)")
    for reason in latest.reasons:
        print(f"- {reason}")
    if latest.owners:
        print(f"owners: {', '.join(latest.owners)}")
    print(
        f"reviewers: {latest.required_reviewers}"
        + (" (deeper verification)" if latest.deeper_verification else "")
    )
    return 0


def cmd_gate_list(args: argparse.Namespace) -> int:
    events = _queue(args).events(args.task_id)
    decisions = [
        {"seq": event.seq, "type": event.type, **event.data}
        for event in events
        if event.type in ("decision.made", "decision.shadow", "would_block")
    ]
    if args.json:
        _emit({"task_id": args.task_id, "events": decisions})
        return 0
    print(
        table(
            ("seq", "type", "gate", "detail"),
            [
                (
                    item["seq"],
                    item["type"],
                    item.get("gate", "-"),
                    item.get("action") or item.get("reason") or item.get("agree") or "-",
                )
                for item in decisions
            ],
        )
    )
    return 0


def cmd_gate_report(args: argparse.Namespace) -> int:
    queue = _queue(args)
    task_ids = [args.task_id] if args.task_id else [task.id for task in queue.list_tasks()]
    report: list[dict[str, Any]] = []
    for task_id in task_ids:
        decisions = [
            event
            for event in queue.events(task_id)
            if event.type in ("decision.made", "decision.shadow", "would_block")
        ]
        by_gate: dict[str, dict[str, int]] = {}
        for event in decisions:
            gate = str(event.data.get("gate", "unknown"))
            bucket = by_gate.setdefault(gate, {"decisions": 0, "would_block": 0, "disagree": 0})
            if event.type == "decision.made":
                bucket["decisions"] += 1
            elif event.type == "would_block":
                bucket["would_block"] += 1
            elif event.data.get("agree") is False:
                bucket["disagree"] += 1
        report.append({"task_id": task_id, "gates": by_gate})
    if args.json:
        _emit({"report": report})
        return 0
    rows = [
        (
            item["task_id"],
            gate,
            counts["decisions"],
            counts["would_block"],
            counts["disagree"],
        )
        for item in report
        for gate, counts in sorted(item["gates"].items())
    ]
    print(table(("task", "gate", "decisions", "would_block", "disagree"), rows))
    return 0
