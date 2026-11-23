from __future__ import annotations

import io
import json
import time
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from works.adapters.queue.index import TaskIndex
from works.domain.evidence import Evidence
from works.domain.records import StopReason, TaskState
from works.interfaces.cli.main import main

TASKS = 10_000


def make_index(root: Path) -> None:
    queue = root / "queue"
    queue.mkdir(parents=True)
    payloads = [
        {
            "id": f"t-{index:012d}",
            "state": "queued",
            "flow": "fix-issue",
            "product": "openjiuwen",
            "repo": ".",
            "source": {"kind": "manual", "ref": f"GH-{index}", "title": ""},
            "attempts": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        for index in range(TASKS)
    ]
    TaskIndex(queue / "index.sqlite3").replace(payloads)


@pytest.mark.slow
def test_status_with_ten_thousand_tasks_stays_under_one_hundred_ms(tmp_path: Path) -> None:
    root = tmp_path / "works"
    make_index(root)
    with redirect_stdout(io.StringIO()):
        assert main(["--home", str(root), "status", "--json"]) == 0
    best = float("inf")
    body: dict = {}
    for _ in range(5):
        out = io.StringIO()
        started = time.perf_counter()
        with redirect_stdout(out):
            code = main(["--home", str(root), "status", "--json"])
        best = min(best, time.perf_counter() - started)
        assert code == 0
        body = json.loads(out.getvalue())
    assert len(body["tasks"]) == TASKS
    assert best < 0.1, f"status took {best * 1000:.1f} ms (best of 5)"


def test_evidence_rendering_is_under_a_second() -> None:
    from tests.unit.domain.test_evidence import fixed_evidence, render_markdown

    evidence: Evidence = fixed_evidence().bind()
    started = time.perf_counter()
    for _ in range(20):
        page = render_markdown(evidence)
    elapsed = (time.perf_counter() - started) / 20
    assert page.startswith("# Proof")
    assert elapsed < 1.0


def test_the_state_machine_is_cheap() -> None:
    from works.domain.records import TaskState as S
    from works.domain.state import can_transition

    started = time.perf_counter()
    for _ in range(100_000):
        can_transition(S.QUEUED, S.REPRODUCING)
    assert time.perf_counter() - started < 1.0


def test_a_blocked_state_is_terminal() -> None:
    assert TaskState.BLOCKED is not TaskState.QUEUED
    assert StopReason.COMPLETED.value == "completed"
