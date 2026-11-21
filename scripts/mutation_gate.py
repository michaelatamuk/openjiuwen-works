"""Mutation gate: killed / considered mutants must be at least 70%.

Mutmut does not run natively on Windows; this script is used by the weekly Linux workflow.
It reads mutmut's own stored results (`mutants/**/*.meta`), not terminal output, so the gate does
not depend on a UI format.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

THRESHOLD = 0.70

# mutmut's status_by_exit_code, condensed to what the gate needs.
KILLED = {1, 3, 37}
EXCLUDED = {2, 34}  # interrupted by the user; skipped by a pragma
STATUS = {
    0: "survived",
    1: "killed",
    2: "interrupted",
    3: "killed",
    5: "no tests",
    33: "no tests",
    34: "skipped",
    35: "suspicious",
    36: "timeout",
    37: "caught by type check",
    -24: "timeout",
    24: "timeout",
    152: "timeout",
}


def _statuses() -> Counter[str]:
    counted: Counter[str] = Counter()
    for meta in Path("mutants").rglob("*.meta"):
        try:
            payload: Any = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        codes = payload.get("exit_code_by_key")
        if not isinstance(codes, dict):
            continue
        for code in codes.values():
            if code is None or code in EXCLUDED:
                continue
            counted[STATUS.get(int(code), f"exit {code}")] += 1
    return counted


def main() -> int:
    run = subprocess.run(["mutmut", "run"], text=True, capture_output=True, check=False)
    print(run.stdout[-4000:])
    if run.returncode != 0:
        print(run.stderr[-4000:], file=sys.stderr)
    counted = _statuses()
    total = sum(counted.values())
    killed = sum(counted[status] for status in ("killed", "caught by type check"))
    score = killed / total if total else 0.0
    print("statuses:", dict(counted))
    print(f"mutation score: {score:.1%} ({killed}/{total}); threshold {THRESHOLD:.0%}")
    if total == 0:
        print("no mutants were considered; failing the gate", file=sys.stderr)
        return 1
    return 0 if score >= THRESHOLD else 1


if __name__ == "__main__":
    raise SystemExit(main())
