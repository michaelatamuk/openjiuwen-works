"""`proof` command registration."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.interfaces.cli.commands.proof import cmd_proof


def add_proof_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    proof = sub.add_parser("proof", help="Verify, export or compare a run's proof")
    proof.add_argument("action", choices=["verify", "export", "diff", "summary"])
    proof.add_argument("run", help="run id")
    proof.add_argument("other", nargs="?", help="second run id for diff")
    proof.add_argument("--out", type=Path, default=None, help="export target")
    proof.add_argument("--json", action="store_true")
    proof.set_defaults(func=cmd_proof)
