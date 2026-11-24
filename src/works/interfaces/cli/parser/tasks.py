"""`tasks` command registration."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.interfaces.cli.commands.tasks import (
    cmd_finding_add,
    cmd_finding_list,
    cmd_status,
    cmd_submit,
    cmd_task,
    cmd_trace,
    cmd_version,
)


def add_tasks_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    version = sub.add_parser("version", help="Print the version")
    version.add_argument("--json", action="store_true")
    version.set_defaults(func=cmd_version)

    submit = sub.add_parser("submit", help="Submit a signal; duplicate sources return one task")
    submit.add_argument("--ref", "-r", required=True, help="Source reference, e.g. GH-42")
    submit.add_argument("--title", "-t", default="", help="One-line title")
    submit.add_argument("--flow", default="fix-issue")
    submit.add_argument("--product", default="openjiuwen")
    submit.add_argument("--repo", type=Path, default=None)
    submit.add_argument("--kind", default="manual", help="manual, tracker or detector")
    submit.add_argument(
        "--task-kind",
        default="fix",
        choices=("fix", "check-change"),
        help="fix or check-change",
    )
    submit.add_argument("--json", action="store_true")
    submit.set_defaults(func=cmd_submit)

    status = sub.add_parser("status", help="Show one task or the queue")
    status.add_argument("task_id", nargs="?", default=None)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    task = sub.add_parser("task", help="Print the task projection")
    task.add_argument("task_id")
    task.add_argument("--json", action="store_true")
    task.set_defaults(func=cmd_task)

    trace = sub.add_parser("trace", help="Render the event timeline")
    trace.add_argument("task_id")
    trace.add_argument("--json", action="store_true")
    trace.set_defaults(func=cmd_trace)

    finding = sub.add_parser("finding", help="Structured findings for a task")
    finding_sub = finding.add_subparsers(dest="finding_command", required=True)
    finding_add = finding_sub.add_parser("add", help="Record a finding")
    finding_add.add_argument("task_id")
    finding_add.add_argument("--summary", required=True)
    finding_add.add_argument("--step", default="")
    finding_add.add_argument("--confidence", default=None)
    finding_add.add_argument("--uncertainty", default="")
    finding_add.add_argument("--evidence", action="append", default=[])
    finding_add.add_argument("--json", action="store_true")
    finding_add.set_defaults(func=cmd_finding_add)
    finding_list = finding_sub.add_parser("list", help="List findings")
    finding_list.add_argument("task_id")
    finding_list.add_argument("--json", action="store_true")
    finding_list.set_defaults(func=cmd_finding_list)
