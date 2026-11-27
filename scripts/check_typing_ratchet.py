"""Typing ratchet: no new explicit `Any` and no new `Any` returns.

The codebase still has a bounded amount of `Any` at adapter and API boundaries. Removing it all at
once would be a rewrite, so the gate records the current count per file and fails when a file or the
total grows. The baseline may only shrink.

    python scripts/check_typing_ratchet.py            # compare with the baseline
    python scripts/check_typing_ratchet.py --update   # after removing Any on purpose
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "reference" / "generated" / "typing-baseline.json"
FLAGS = ("--disallow-any-explicit", "--warn-return-any")
ERRORS = frozenset({"explicit-any", "no-any-return"})
LINE = re.compile(r"^(?P<file>[^:]+):\d+: error: .*\[(?P<code>[a-z-]+)\]$")


def parse(output: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in output.splitlines():
        match = LINE.match(line.strip())
        if match is None or match.group("code") not in ERRORS:
            continue
        name = match.group("file").replace("\\", "/")
        counts[name] = counts.get(name, 0) + 1
    return counts


def measure() -> dict[str, int]:
    completed = subprocess.run(  # nosec B603
        [sys.executable, "-m", "mypy", "src", *FLAGS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return parse(completed.stdout + completed.stderr)


def load() -> dict[str, Any]:
    if not BASELINE.exists():
        return {"schema_version": 1, "files": {}}
    payload: Any = json.loads(BASELINE.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"schema_version": 1, "files": {}}


def regressions(current: dict[str, int], baseline: dict[str, Any]) -> list[str]:
    recorded: dict[str, int] = {
        str(name): int(count) for name, count in (baseline.get("files") or {}).items()
    }
    found: list[str] = []
    for name, count in sorted(current.items()):
        allowed = recorded.get(name, 0)
        if count > allowed:
            found.append(f"{name}: {count} Any error(s), baseline {allowed}")
    current_total = sum(current.values())
    baseline_total = sum(recorded.values())
    if current_total > baseline_total:
        found.append(f"total: {current_total}, baseline {baseline_total}")
    return found


def write(current: dict[str, int]) -> None:
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "flags": list(FLAGS),
        "total": sum(current.values()),
        "files": dict(sorted(current.items())),
    }
    BASELINE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="record the current counts")
    args = parser.parse_args()
    current = measure()
    if args.update:
        write(current)
        print(f"recorded {sum(current.values())} Any error(s) in {len(current)} file(s)")
        return 0
    found = regressions(current, load())
    if found:
        print("\n".join(found))
        print("remove the new Any or, if the baseline is wrong, run --update on purpose")
        return 1
    print(f"typing ratchet holds: {sum(current.values())} Any error(s), no growth")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
