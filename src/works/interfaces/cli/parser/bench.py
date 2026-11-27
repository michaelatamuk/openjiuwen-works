"""`bench` command registration."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.interfaces.cli.commands.bench import cmd_bench


def add_bench_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    bench = sub.add_parser("bench", help="Run the pipeline over a local case dataset")
    bench.add_argument("--dataset", required=True, type=Path, help="JSONL cases")
    bench.add_argument("--workdir", type=Path, default=None)
    bench.add_argument("--keep", action="store_true", help="Keep the isolated homes")
    bench.add_argument("--json", action="store_true")
    bench.set_defaults(func=cmd_bench)
