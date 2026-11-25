"""`estimate` command registration."""

from __future__ import annotations

import argparse

from works.interfaces.cli.commands.estimate import cmd_estimate_backtest


def add_estimate_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    estimate = sub.add_parser("estimate", help="Inspect the scheduler's duration estimates")
    commands = estimate.add_subparsers(dest="estimate_command", required=True)

    backtest = commands.add_parser(
        "backtest",
        help="Leave-one-out calibration over stored runs",
    )
    backtest.add_argument("--min-samples", type=int, default=5)
    backtest.add_argument("--min-coverage", type=float, default=0.8)
    backtest.add_argument("--json", action="store_true")
    backtest.set_defaults(func=cmd_estimate_backtest)
