from __future__ import annotations

import asyncio
from pathlib import Path

from works.domain.records import StopReason, TaskState

FLIP = """import pathlib

counter = pathlib.Path(__file__).with_suffix(".count")
value = int(counter.read_text()) if counter.exists() else 0
counter.write_text(str(value + 1))
raise SystemExit(0 if value % 2 == 1 else 1)
"""

STEADY = "raise SystemExit(0)\n"


def _scenario_set(tmp_path: Path, script: str) -> Path:
    directory = tmp_path / "scenarios"
    directory.mkdir()
    (directory / "flip.py").write_text(script, encoding="utf-8")
    path = directory / "set.yaml"
    path.write_text(
        "schema_version: 1\n"
        "flow: fix-issue\n"
        "directory: '.'\n"
        "scenarios:\n"
        "  - id: flip\n"
        "    priority: P0\n"
        "    script: flip.py\n",
        encoding="utf-8",
    )
    return path


def _run(supervisor, task_id: str, scenario_set: Path):
    return asyncio.run(supervisor.run(task_id, scenario_set=scenario_set, approve_plan=True))


def test_a_mixed_result_is_unstable(paths, submit, make_supervisor, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKS_REPEAT_SCENARIOS", "2")
    scenario_set = _scenario_set(tmp_path, FLIP)
    task = submit()

    record = _run(make_supervisor("fix-add"), task.id, scenario_set)

    assert record.state is TaskState.BLOCKED
    assert record.stop_reason is StopReason.FLAKY_TEST


def test_a_stable_result_completes(paths, submit, make_supervisor, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKS_REPEAT_SCENARIOS", "2")
    scenario_set = _scenario_set(tmp_path, STEADY)
    task = submit()

    record = _run(make_supervisor("fix-add"), task.id, scenario_set)

    assert record.stop_reason is StopReason.COMPLETED


def test_one_run_by_default(paths, submit, make_supervisor, tmp_path) -> None:
    scenario_set = _scenario_set(tmp_path, FLIP)
    task = submit()

    record = _run(make_supervisor("fix-add"), task.id, scenario_set)

    assert record.stop_reason is StopReason.VERDICT_FAILED
