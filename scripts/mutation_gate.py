"""Mutation gate: killed / considered mutants must be at least 70%.

Mutmut does not run natively on Windows; this script is used by the weekly Linux workflow.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter

THRESHOLD = 0.70
LINE = re.compile(r"^\s+(.+): ([a-z][a-z ]*)$", re.MULTILINE)
EXCLUDED = {"skipped", "not checked", "check was interrupted by user"}


def main() -> int:
    run = subprocess.run(["mutmut", "run"], text=True, capture_output=True, check=False)
    print(run.stdout[-4000:])
    if run.returncode != 0:
        print(run.stderr[-4000:], file=sys.stderr)
    results = subprocess.run(
        ["mutmut", "results", "--all"], text=True, capture_output=True, check=False
    )
    statuses = LINE.findall(results.stdout)
    counted = [status for status in statuses if status not in EXCLUDED]
    killed = sum(1 for status in counted if status in ("killed", "caught by type check"))
    total = len(counted)
    score = killed / total if total else 0.0
    print("statuses:", dict(Counter(counted)))
    print(f"mutation score: {score:.1%} ({killed}/{total}); threshold {THRESHOLD:.0%}")
    if total == 0:
        print("no mutants were considered; failing the gate", file=sys.stderr)
        return 1
    return 0 if score >= THRESHOLD else 1


if __name__ == "__main__":
    raise SystemExit(main())
