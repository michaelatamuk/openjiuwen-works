"""CLI command group."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from works.domain.errors import (
    EXIT_BLOCKED,
    EXIT_POLICY,
)
from works.interfaces.cli.commands.common import _emit, _paths
from works.interfaces.cli.render import table


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
