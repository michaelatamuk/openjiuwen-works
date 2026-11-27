"""`works bench` — run the pipeline over a local case dataset."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from works.application.bench import load_cases, run_bench
from works.interfaces.cli.commands.common import _emit, _paths


def cmd_bench(args: argparse.Namespace) -> int:
    _paths(args)
    dataset = Path(args.dataset).expanduser().resolve()
    cases = load_cases(dataset)
    result = run_bench(cases, workdir=args.workdir, keep=args.keep)
    if args.json:
        _emit(
            {
                "cases": result.cases,
                "resolved": result.resolved,
                "rate": round(result.rate, 4),
                "bound": result.bound,
                "total_usd": result.total_usd,
                "results": [asdict(item) for item in result.results],
            }
        )
        return 0
    for item in result.results:
        state = "ok" if item.ok else "FAIL"
        print(
            f"{state:4} {item.id} · {item.state or '-'} · "
            f"verdict {item.verdict_allow if item.verdict_allow is not None else '-'} · "
            f"proof {'bound' if item.proof_bound else 'unbound'} · ${item.usd:.2f}"
            + (f" · {item.error}" if item.error else "")
        )
    print(
        f"bench: {result.resolved}/{result.cases} resolved ({result.rate:.0%}) · "
        f"{result.bound} proof(s) bound · ${result.total_usd:.2f}"
    )
    if result.cases == 0:
        print("no cases in the dataset")
    return 0
