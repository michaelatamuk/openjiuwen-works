"""`run` command registration."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.interfaces.cli.commands.gates import cmd_policy_check
from works.interfaces.cli.commands.run import (
    cmd_dispatch,
    cmd_run,
    cmd_wait,
    cmd_wake,
)


def add_run_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    run = sub.add_parser("run", help="Reproduce, plan, build, check, prove")
    run.add_argument("task_id")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--approve-plan", action="store_true")
    run.add_argument("--scenarios", default=None)
    run.add_argument("--quarantine", default=None)
    run.add_argument("--trace", type=Path, default=None)
    run.add_argument("--live", action="store_true")
    run.add_argument("--swarm", action="store_true")
    run.add_argument("--swarm-python", default=None)
    run.add_argument("--swarm-home", default=None)
    run.add_argument("--model", default=None)
    run.add_argument("--model-base", default=None)
    run.add_argument("--prompt", type=Path, default=None)
    run.add_argument("--ppma", default=None)
    run.add_argument("--ppma-space", default="me")
    run.add_argument("--decision", choices=("off", "shadow", "laix"), default=None)
    run.add_argument("--verifier", choices=("local", "docker"), default="local")
    run.add_argument("--verifier-image", default=None)
    run.add_argument(
        "--daemon",
        action="store_true",
        help="Run through the local daemon instead of in this process",
    )
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)

    wait = sub.add_parser("wait", help="Put a task into a waiting state")
    wait.add_argument("task_id")
    wait.add_argument("--on", choices=("review", "ci", "deploy"), required=True)
    wait.add_argument("--wake-on", required=True)
    wait.add_argument("--deadline", default=None)
    wait.add_argument("--next", default=None)
    wait.add_argument("--default", default=None)
    wait.add_argument("--json", action="store_true")
    wait.set_defaults(func=cmd_wait)

    wake = sub.add_parser("wake", help="Wake a waiting task on its event")
    wake.add_argument("task_id")
    wake.add_argument("--event", required=True)
    wake.add_argument("--json", action="store_true")
    wake.set_defaults(func=cmd_wake)

    dispatch = sub.add_parser("dispatch", help="Claim and run ready tasks")
    dispatch.add_argument("--limit", type=int, default=10)
    dispatch.add_argument("--watch", action="store_true")
    dispatch.add_argument("--interval", type=int, default=10)
    dispatch.add_argument("--approve-plan", action="store_true")
    dispatch.add_argument("--scenarios", default=None)
    dispatch.add_argument("--quarantine", default=None)
    dispatch.add_argument("--trace", type=Path, default=None)
    dispatch.add_argument("--live", action="store_true")
    dispatch.add_argument("--swarm", action="store_true")
    dispatch.add_argument("--swarm-python", default=None)
    dispatch.add_argument("--swarm-home", default=None)
    dispatch.add_argument("--model", default=None)
    dispatch.add_argument("--model-base", default=None)
    dispatch.add_argument("--prompt", type=Path, default=None)
    dispatch.add_argument("--ppma", default=None)
    dispatch.add_argument("--ppma-space", default="me")
    dispatch.add_argument("--decision", choices=("off", "shadow", "laix"), default=None)
    dispatch.add_argument("--verifier", choices=("local", "docker"), default="local")
    dispatch.add_argument("--verifier-image", default=None)
    dispatch.add_argument(
        "--daemon",
        action="store_true",
        help="Dispatch through the local daemon instead of in this process",
    )
    dispatch.add_argument("--json", action="store_true")
    dispatch.set_defaults(func=cmd_dispatch)

    policy = sub.add_parser("policy", help="Path policy")
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    check = policy_sub.add_parser("check", help="Check paths before any command runs")
    check.add_argument("paths", nargs="+")
    check.add_argument("--flow", default=None)
    check.add_argument("--json", action="store_true")
    check.set_defaults(func=cmd_policy_check)
