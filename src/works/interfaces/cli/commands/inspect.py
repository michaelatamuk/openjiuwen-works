"""CLI command group."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from works.domain.errors import (
    EXIT_BLOCKED,
    EXIT_POLICY,
    ConfigError,
)
from works.interfaces.cli.commands.common import _emit, _paths, _queue
from works.interfaces.cli.render import table

if TYPE_CHECKING:
    pass


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


def cmd_flake_add(args: argparse.Namespace) -> int:
    from works.application.execution.flakes import add_flake

    flake = add_flake(
        _paths(args),
        task_id=args.task_id,
        scenario_id=args.scenario,
        owner=args.owner,
        reason=args.reason,
        days=args.days,
    )
    if args.json:
        _emit({"flake": flake.model_dump(mode="json")})
    else:
        print(f"flake recorded: {flake.id} ({flake.scenario_id}, owner {flake.owner})")
    return 0


def cmd_flake_list(args: argparse.Namespace) -> int:
    from works.application.execution.flakes import active_flakes, load_flakes

    flakes = active_flakes(_paths(args)) if args.active else load_flakes(_paths(args))
    if args.json:
        _emit({"flakes": [flake.model_dump(mode="json") for flake in flakes]})
        return 0
    print(
        table(
            ("id", "task", "scenario", "owner", "expires", "status"),
            [
                (
                    flake.id,
                    flake.task_id,
                    flake.scenario_id,
                    flake.owner,
                    flake.expires_at.isoformat(timespec="seconds") if flake.expires_at else "-",
                    flake.status.value,
                )
                for flake in flakes
            ],
        )
    )
    return 0


def cmd_decision_replay(args: argparse.Namespace) -> int:
    from works.application.approvals.decisions import build_decision_port
    from works.application.approvals.eval import load_cases, replay, summary

    cases = load_cases(Path(args.cases))
    candidate = build_decision_port(args.provider)
    outcomes = replay(cases, candidate)
    payload = summary(outcomes)
    if args.json:
        _emit(payload)
    else:
        print(
            table(
                ("case", "deterministic", "candidate", "agree", "unsafe"),
                [
                    (
                        item.case_id,
                        item.deterministic.action,
                        item.candidate.action,
                        "yes" if item.agree else "no",
                        "YES" if item.unsafe_allow else "no",
                    )
                    for item in outcomes
                ],
            )
        )
        print(
            f"{payload['cases']} cases · {payload['agree']} agree · "
            f"{payload['disagree']} differ · {payload['unsafe_allow']} unsafe allow"
        )
    return EXIT_POLICY if payload["unsafe_allow"] else 0


def cmd_readiness(args: argparse.Namespace) -> int:
    from works.application.execution.readiness import assess

    repo = Path(args.repo or ".").expanduser()
    report = assess(repo, run_commands=not args.no_run, timeout_s=args.timeout)
    if args.json:
        payload = {"ok": report.status != "fail", **report.as_dict()}
        print(json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":")))
    else:
        print(f"Readiness: {report.status.upper()} ({report.passed}/{report.total})")
        for check in report.checks:
            mark = "✓" if check.status == "pass" else "!" if check.status == "fail" else "-"
            detail = f" - {check.detail}" if check.detail else ""
            print(f"  {mark} {check.label}{detail}")
        if report.unknown_suppressions:
            print("  Unknown suppressions:")
            for item in report.unknown_suppressions[:20]:
                print(f"    {item.location}  {item.text}")
        print(f"  {report.note}")
    return EXIT_BLOCKED if report.status == "fail" else 0
