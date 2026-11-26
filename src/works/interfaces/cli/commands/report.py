"""`works report` — the numbers the deck promises, from the local history."""

from __future__ import annotations

import argparse

from works.application.report import as_dict, build_report, format_minutes
from works.interfaces.cli.commands.common import _emit, _paths


def cmd_report(args: argparse.Namespace) -> int:
    report = build_report(_paths(args), days=args.days)
    if args.json:
        _emit(as_dict(report))
        return 0
    print(f"Works report · last {report.days} days · {report.generated_at.date().isoformat()}")
    states = ", ".join(f"{name} {count}" for name, count in report.by_state.items()) or "none"
    print(f"Tasks {report.tasks}: {states}")
    print(
        f"Runs {report.runs} · ${report.total_usd:.2f} total · "
        + (
            f"${report.per_released_usd:.2f} per released change"
            if report.per_released_usd is not None
            else "no released change yet"
        )
    )
    timing = report.time_to_release
    print(
        "Time to release: "
        f"median {format_minutes(timing.median_min)} · p90 {format_minutes(timing.p90_min)} "
        f"({timing.samples} change(s))"
    )
    plan = report.gates.get("plan", {})
    release = report.gates.get("release", {})
    print(
        "Gates: plan "
        f"{plan.get('approved', 0)}/{plan.get('changes_requested', 0)}/"
        f"{plan.get('rejected', 0)} · release "
        f"{release.get('approved', 0)}/{release.get('changes_requested', 0)}/"
        f"{release.get('rejected', 0)} (approved/changes/rejected)"
    )
    print(
        f"Reopens {report.reopens} · CVE {report.cve_tasks} "
        f"({report.cve_released} released) · escapes {report.escapes} · rework {report.rework}"
    )
    if report.stop_reasons:
        stops = ", ".join(f"{name} {count}" for name, count in report.stop_reasons.items())
        print(f"Stops: {stops}")
    return 0
