"""`plan` command registration."""

from __future__ import annotations

import argparse

from works.interfaces.cli.commands.plan import cmd_approve, cmd_plan


def add_plan_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    plan = sub.add_parser("plan", help="Draft, show, lint or diff versioned plans")
    plan.add_argument("task_id")
    plan.add_argument("--action", choices=("draft", "show", "lint", "diff"), default="draft")
    plan.add_argument("--scenarios", default=None)
    plan.add_argument("--version", type=int, default=None)
    plan.add_argument("--from", dest="from_version", type=int, default=None)
    plan.add_argument("--to", dest="to_version", type=int, default=None)
    plan.add_argument(
        "--mode",
        choices=("deterministic", "shadow", "assisted", "deep", "spec", "auto"),
        default=None,
    )
    plan.add_argument("--model", default=None)
    plan.add_argument("--model-base", default=None)
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(func=cmd_plan)

    approve = sub.add_parser("approve", help="Approve the plan gate")
    approve.add_argument("task_id")
    approve.add_argument("--gate", default="plan", help="plan or release")
    approve.add_argument("--plan", default=None, help="Plan id to approve (default: latest)")
    approve.add_argument("--plan-hash", default=None, help="Exact plan hash to approve")
    approve.add_argument("--json", action="store_true")
    approve.set_defaults(func=cmd_approve)
