"""`estimate` commands: the calibration guardrail for the scheduler's numbers."""

from __future__ import annotations

import argparse
from typing import cast

from works.application.scheduling.estimates import backtest, read_samples
from works.application.scheduling.promotion import promote, readiness
from works.interfaces.cli.commands.common import _emit, _paths


def cmd_estimate_backtest(args: argparse.Namespace) -> int:
    samples = read_samples(_paths(args))
    report = backtest(samples, min_samples=args.min_samples)
    total = cast(int, report["samples"])
    coverage = cast(float, report["coverage_p90"])
    pinball = cast(float, report["pinball"])
    tails = cast(int, report["tail_misses"])
    in_band = 0.85 <= coverage <= 0.95
    failed = total >= args.min_samples and not in_band
    if args.json:
        _emit(
            {
                "samples": total,
                "coverage_p90": coverage,
                "pinball": pinball,
                "tail_misses": tails,
                "groups": report["groups"],
                "min_coverage": args.min_coverage,
                "ok": not failed,
            }
        )
        return 1 if failed else 0
    print(f"samples: {total} · tail misses: {tails}")
    print(f"p90 coverage: {coverage:.0%} (expected band 85%..95%)")
    print(f"pinball loss: {pinball:.1f} minutes")
    groups = cast(list[dict[str, object]], report["groups"])
    for group in groups:
        print(
            f"  {group['group']}: n={group['samples']} "
            f"coverage={float(cast(float, group['coverage_p90'])):.0%} "
            f"tails={group['tail_misses']}"
        )
    if total < args.min_samples:
        print("not enough history to judge; the estimator is untested")
        return 0
    if failed:
        print("FAIL: p90 coverage is outside 85%..95%; the tail is mis-sized")
        return 1
    print("ok")
    return 0


def cmd_estimate_promotion(args: argparse.Namespace) -> int:
    report = readiness(_paths(args))
    if args.json:
        _emit(report)
        return 0 if report["ready"] else 1
    print(f"shadow claims: {report['shadow_claims']} · weeks: {report['weeks']:.1f}")
    print(f"agreement: {report['agreement']:.0%} · p90 coverage: {report['coverage']:.0%}")
    for name, passed in cast(dict[str, bool], report["checks"]).items():
        print(f"  {'ok ' if passed else 'NO '} {name}")
    print("ready to promote" if report["ready"] else "not ready; the rules keep deciding")
    return 0 if report["ready"] else 1


def cmd_estimate_promote(args: argparse.Namespace) -> int:
    record = promote(_paths(args), by=args.by, device=args.device)
    if args.json:
        _emit({"ok": True, "promotion": record})
    else:
        print(f"learned order promoted by {record['by']} on {record['device']}")
    return 0
