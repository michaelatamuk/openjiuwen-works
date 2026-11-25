"""Measure the frontend build with and without React Compiler.

The compiler is opt-in (`WORKS_REACT_COMPILER=1`). This script builds both ways, records bundle
size, file count and build time, and prints the delta. A growth over `--max-growth` percent fails,
so the compiler cannot quietly ship a larger bundle.

    python scripts/measure_web.py
    python scripts/measure_web.py --max-growth 5
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
DIST = ROOT / "src" / "works" / "interfaces" / "ui" / "static" / "dist"
REPORT = WEB / ".compiler-report.json"


def build(enabled: bool) -> dict[str, Any]:
    env = {**os.environ, "WORKS_REACT_COMPILER": "1" if enabled else "0"}
    started = time.perf_counter()
    completed = subprocess.run(  # noqa: S602  # nosec B602 B603
        "npm run build",
        cwd=WEB,
        shell=True,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    seconds = time.perf_counter() - started
    if completed.returncode != 0:
        print(completed.stdout[-2000:])
        print(completed.stderr[-2000:], file=sys.stderr)
        raise SystemExit("the build failed")
    files = [path for path in DIST.rglob("*") if path.is_file()]
    sizes = {path: path.stat().st_size for path in files}
    return {
        "compiler": enabled,
        "seconds": round(seconds, 2),
        "files": len(files),
        "total_bytes": sum(sizes.values()),
        "js_bytes": sum(size for path, size in sizes.items() if path.suffix == ".js"),
        "css_bytes": sum(size for path, size in sizes.items() if path.suffix == ".css"),
        "largest": max(files, key=lambda path: sizes[path]).name if files else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-growth", type=float, default=5.0, help="allowed bundle growth in %")
    args = parser.parse_args()

    base = build(False)
    compiled = build(True)
    growth = (
        (compiled["total_bytes"] - base["total_bytes"]) / base["total_bytes"] * 100
        if base["total_bytes"]
        else 0.0
    )
    report = {"base": base, "compiled": compiled, "growth_percent": round(growth, 2)}
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")

    print(f"{'build':<10}{'seconds':>10}{'files':>8}{'total':>12}{'js':>12}{'css':>10}")
    for row in (base, compiled):
        print(
            f"{'compiler' if row['compiler'] else 'plain':<10}"
            f"{row['seconds']:>10.2f}{row['files']:>8}"
            f"{row['total_bytes']:>12}{row['js_bytes']:>12}{row['css_bytes']:>10}"
        )
    print(f"growth: {growth:+.2f}% (limit {args.max_growth:.1f}%)")
    return 1 if growth > args.max_growth else 0


if __name__ == "__main__":
    raise SystemExit(main())
