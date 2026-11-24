"""`inspect` command registration."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.interfaces.cli.commands.gates import (
    cmd_gate_list,
    cmd_gate_report,
    cmd_risk,
)
from works.interfaces.cli.commands.inspect import (
    cmd_doctor,
    cmd_escapes,
    cmd_ledger,
    cmd_metrics,
    cmd_schema,
)
from works.interfaces.cli.commands.quality import (
    cmd_decision_replay,
    cmd_flake_add,
    cmd_flake_list,
    cmd_readiness,
)


def add_inspect_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    metrics = sub.add_parser("metrics", help="Attention and cost metrics")
    metrics.add_argument("--json", action="store_true")
    metrics.set_defaults(func=cmd_metrics)

    escapes = sub.add_parser("escapes", help="Attribute reverts, hotfixes and repeated work")
    escapes.add_argument("--days", type=int, default=14)
    escapes.add_argument("--dry-run", action="store_true", help="Scan without writing the report")
    escapes.add_argument("--json", action="store_true")
    escapes.set_defaults(func=cmd_escapes)

    ledger = sub.add_parser("ledger", help="Read the append-only ledger")
    ledger.add_argument("--json", action="store_true")
    ledger.set_defaults(func=cmd_ledger)

    schema = sub.add_parser("schema", help="Print every persisted schema")
    schema.add_argument("--json", action="store_true")
    schema.set_defaults(func=cmd_schema)

    doctor = sub.add_parser("doctor", help="Check config, git, harness, container, credentials")
    doctor.add_argument("--repo", type=Path, default=None)
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--bundle", type=Path, default=None, help="Write a redacted debug bundle")
    doctor.set_defaults(func=cmd_doctor)

    risk = sub.add_parser("risk", help="Show the latest risk rating")
    risk.add_argument("task_id")
    risk.add_argument("--json", action="store_true")
    risk.set_defaults(func=cmd_risk)

    gate = sub.add_parser("gate", help="Inspect gate decisions and observe-mode blocks")
    gate_sub = gate.add_subparsers(dest="gate_command", required=True)
    gate_list = gate_sub.add_parser("list", help="List decisions for a task")
    gate_list.add_argument("task_id")
    gate_list.add_argument("--json", action="store_true")
    gate_list.set_defaults(func=cmd_gate_list)
    gate_report = gate_sub.add_parser("report", help="Summarize decisions and observe blocks")
    gate_report.add_argument("task_id", nargs="?", default=None)
    gate_report.add_argument("--json", action="store_true")
    gate_report.set_defaults(func=cmd_gate_report)

    flake = sub.add_parser("flake", help="Flaky tests are defects with an owner and an expiry")
    flake_sub = flake.add_subparsers(dest="flake_command", required=True)
    flake_add = flake_sub.add_parser("add", help="Record a flake")
    flake_add.add_argument("task_id")
    flake_add.add_argument("--scenario", required=True)
    flake_add.add_argument("--owner", required=True)
    flake_add.add_argument("--reason", required=True)
    flake_add.add_argument("--days", type=int, default=14)
    flake_add.add_argument("--json", action="store_true")
    flake_add.set_defaults(func=cmd_flake_add)
    flake_list = flake_sub.add_parser("list", help="List flakes")
    flake_list.add_argument("--active", action="store_true")
    flake_list.add_argument("--json", action="store_true")
    flake_list.set_defaults(func=cmd_flake_list)

    decision = sub.add_parser("decision", help="Replay historical gate cases")
    decision_sub = decision.add_subparsers(dest="decision_command", required=True)
    decision_replay = decision_sub.add_parser(
        "replay", help="Compare a candidate policy with the rule"
    )
    decision_replay.add_argument("--cases", required=True)
    decision_replay.add_argument("--provider", choices=("off", "shadow", "laix"), default="laix")
    decision_replay.add_argument("--json", action="store_true")
    decision_replay.set_defaults(func=cmd_decision_replay)

    readiness = sub.add_parser(
        "readiness", help="Decide whether a repository is ready for autonomous work"
    )
    readiness.add_argument("--repo", type=Path, default=None)
    readiness.add_argument("--no-run", action="store_true", help="Static checks only")
    readiness.add_argument("--timeout", type=int, default=120)
    readiness.add_argument("--json", action="store_true")
    readiness.set_defaults(func=cmd_readiness)
