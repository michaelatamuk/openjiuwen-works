"""Measure the budgets from the engineering standard. Windows- and Linux-friendly."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def timed_subprocess(argv: list[str], env: dict[str, str], repeats: int = 3) -> float:
    best = float("inf")
    for _ in range(repeats):
        started = time.perf_counter()
        subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, check=False)
        best = min(best, time.perf_counter() - started)
    return best


def status_10k(root: Path) -> float:
    from works.cli import main
    from works.index import TaskIndex

    queue = root / "queue"
    queue.mkdir(parents=True)
    payloads = [
        {
            "id": f"t-{i:012d}",
            "state": "queued",
            "flow": "fix-issue",
            "product": "openjiuwen",
            "repo": ".",
            "source": {"kind": "manual", "ref": f"GH-{i}", "title": ""},
            "attempts": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        for i in range(10_000)
    ]
    TaskIndex(queue / "index.sqlite3").replace(payloads)
    with redirect_stdout(io.StringIO()):
        assert main(["--home", str(root), "status", "--json"]) == 0
    best = float("inf")
    for _ in range(5):
        started = time.perf_counter()
        with redirect_stdout(io.StringIO()):
            assert main(["--home", str(root), "status", "--json"]) == 0
        best = min(best, time.perf_counter() - started)
    return best


def evidence_render() -> float:
    sys.path.insert(0, str(ROOT))
    from tests.test_evidence import fixed_evidence
    from works.evidence import render_markdown

    evidence = fixed_evidence().bind()
    started = time.perf_counter()
    for _ in range(50):
        render_markdown(evidence)
    return (time.perf_counter() - started) / 50


def main() -> int:
    workspace = Path(tempfile.mkdtemp(prefix="works-bench-")) / "workspace"
    env = dict(os.environ)
    env["WORKS_HOME"] = str(workspace)
    env["CI"] = "1"

    python = sys.executable
    help_ms = timed_subprocess([python, "-m", "works", "--help"], env) * 1000
    empty_status_ms = timed_subprocess([python, "-m", "works", "status", "--json"], env) * 1000
    status_logic_ms = status_10k(workspace / "ten-thousand") * 1000
    evidence_ms = evidence_render() * 1000

    budgets = {
        "cli_start_ms": help_ms < 300,
        "status_logic_ms": status_logic_ms < 100,
        "evidence_render_ms": evidence_ms < 1000,
    }
    report = {
        "cli_start_ms": round(help_ms, 1),
        "empty_status_process_ms": round(empty_status_ms, 1),
        "status_10k_logic_ms": round(status_logic_ms, 1),
        "evidence_render_ms": round(evidence_ms, 2),
        "budgets": budgets,
        "ok": all(budgets.values()),
    }
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
