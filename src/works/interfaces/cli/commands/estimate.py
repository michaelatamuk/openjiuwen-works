"""`estimate` commands: the calibration guardrail for the scheduler's numbers."""

from __future__ import annotations

import argparse

from works.application.scheduling.estimates import backtest, read_samples
from works.interfaces.cli.commands.common import _emit, _paths


def cmd_estimate_backtest(args: argparse.Namespace) -> int:
    samples = read_samples(_paths(args))
    report = backtest(samples, min_samples=args.min_samples)
    total = int(report["samples"])
    coverage = float(report["coverage_p90"])
    pinball = float(report["pinball"])
    failed = total >= args.min_samples and coverage < args.min_coverage
    if args.json:
        _emit(
            {
                "samples": total,
                "coverage_p90": coverage,
                "pinball": pinball,
                "min_coverage": args.min_coverage,
                "ok": not failed,
            }
        )
        return 1 if failed else 0
    print(f"samples: {total}")
    print(f"p90 coverage: {coverage:.0%} (target >= {args.min_coverage:.0%})")
    print(f"pinball loss: {pinball:.1f} minutes")
    if total < args.min_samples:
        print("not enough history to judge; the estimator is untested")
        return 0
    if failed:
        print("FAIL: the p90 estimate misses too often; do not trust the fit decisions")
        return 1
    print("ok")
    return 0
