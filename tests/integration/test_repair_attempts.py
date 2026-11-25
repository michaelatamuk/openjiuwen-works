from __future__ import annotations

import asyncio
import json
from pathlib import Path

from works.adapters.queue.store import Queue
from works.application.supervisor import Supervisor
from works.domain.records import StopReason, TaskState


def run(supervisor: Supervisor, task_id: str, scenario_set: Path, **kwargs):
    return asyncio.run(supervisor.run(task_id, scenario_set=scenario_set, **kwargs))


def test_a_flow_can_ask_for_a_second_build_attempt(
    paths, submit, scenario_set, make_supervisor
) -> None:
    flow_path = paths.flows / "fix-issue.yaml"
    text = flow_path.read_text(encoding="utf-8")
    assert "repair:\n  attempts: 1" in text
    flow_path.write_text(text.replace("attempts: 1", "attempts: 2"), encoding="utf-8")
    task = submit()

    record = run(make_supervisor("fix-add-sneaky"), task.id, scenario_set, approve_plan=True)

    assert record.state is TaskState.BLOCKED
    assert record.stop_reason is StopReason.VERDICT_FAILED
    events = Queue(paths).events(task.id)
    assert sum(1 for event in events if event.type == "build.started") == 2
    retries = [event for event in events if event.type == "build.retry"]
    assert len(retries) == 1
    assert retries[0].data["attempt"] == 2
    evidence = json.loads(
        (paths.run_dir(record.run_id) / "evidence.json").read_text(encoding="utf-8")
    )
    assert evidence["attempts"] == 2


def test_the_default_flow_still_has_one_attempt(
    paths, submit, scenario_set, make_supervisor
) -> None:
    task = submit()

    record = run(make_supervisor("fix-add-sneaky"), task.id, scenario_set, approve_plan=True)

    assert record.stop_reason is StopReason.VERDICT_FAILED
    events = Queue(paths).events(task.id)
    assert sum(1 for event in events if event.type == "build.started") == 1
    assert not [event for event in events if event.type == "build.retry"]
