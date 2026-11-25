"""`scheduler` command registration."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.interfaces.cli.commands.scheduler import (
    cmd_scheduler_disable,
    cmd_scheduler_enable,
    cmd_scheduler_pause,
    cmd_scheduler_resume,
    cmd_scheduler_status,
    cmd_scheduler_tick,
)


def add_scheduler_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    scheduler = sub.add_parser("scheduler", help="Inspect or drive the queue scheduler")
    commands = scheduler.add_subparsers(dest="scheduler_command", required=True)

    status = commands.add_parser("status", help="Policy, slots, budget and why tasks wait")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_scheduler_status)

    pause = commands.add_parser("pause", help="Stop claiming tasks; the queue is kept")
    pause.add_argument("--reason", default="")
    pause.add_argument("--json", action="store_true")
    pause.set_defaults(func=cmd_scheduler_pause)

    resume = commands.add_parser("resume", help="Resume claiming tasks")
    resume.add_argument("--json", action="store_true")
    resume.set_defaults(func=cmd_scheduler_resume)

    enable = commands.add_parser("enable", help="Write enabled: true into the policy")
    enable.add_argument("--json", action="store_true")
    enable.set_defaults(func=cmd_scheduler_enable)

    disable = commands.add_parser("disable", help="Write enabled: false into the policy")
    disable.add_argument("--json", action="store_true")
    disable.set_defaults(func=cmd_scheduler_disable)

    tick = commands.add_parser("tick", help="Run one selection tick")
    tick.add_argument("--limit", type=int, default=None)
    tick.add_argument("--no-run", action="store_true", help="Only plan the tick; claim nothing")
    tick.add_argument("--json", action="store_true")
    tick.add_argument("--trace", type=Path, default=None)
    tick.add_argument("--live", action="store_true")
    tick.add_argument("--swarm", action="store_true")
    tick.add_argument("--swarm-python", default=None)
    tick.add_argument("--swarm-home", default=None)
    tick.add_argument("--scenarios", default=None)
    tick.add_argument("--quarantine", default=None)
    tick.add_argument("--model", default=None)
    tick.add_argument("--model-base", default=None)
    tick.add_argument("--prompt", type=Path, default=None)
    tick.add_argument("--ppma", default=None)
    tick.add_argument("--ppma-space", default="me")
    tick.add_argument("--decision", choices=("off", "shadow", "laix"), default=None)
    tick.add_argument("--verifier", choices=("local", "docker"), default="local")
    tick.add_argument("--verifier-image", default=None)
    tick.set_defaults(func=cmd_scheduler_tick)
