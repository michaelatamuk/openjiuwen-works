from __future__ import annotations

import json

import pytest

from works.config import WorksPaths
from works.errors import ConflictError, NotFoundError, StateError
from works.queue import EVENTS_FILE, Queue, make_task_id, project
from works.records import Budget, Source, SourceKind, TaskState


def new_queue(paths: WorksPaths) -> Queue:
    return Queue(paths)


def submit(queue: Queue, ref: str = "GH-1") -> object:
    task, created = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref=ref, title="a bug"),
        flow="fix-issue",
        product="openjiuwen",
        repo=".",
    )
    assert created
    return task


def test_submit_is_idempotent(paths: WorksPaths) -> None:
    queue = new_queue(paths)
    first = submit(queue)
    second, created = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="GH-1", title="a different title"),
        flow="fix-issue",
        product="openjiuwen",
        repo=".",
    )
    assert not created
    assert first.id == second.id
    assert len(queue.list_tasks()) == 1


def test_ids_depend_only_on_kind_and_ref() -> None:
    assert make_task_id("manual", "GH-1") == make_task_id("manual", "GH-1")
    assert make_task_id("manual", "GH-1") != make_task_id("tracker", "GH-1")


def test_replay_rebuilds_the_projection(paths: WorksPaths) -> None:
    queue = new_queue(paths)
    task = submit(queue)
    queue.append(task.id, "attempt.started", {})
    queue.transition(task.id, TaskState.REPRODUCING)
    queue.transition(task.id, TaskState.REPRODUCED)
    queue.transition(task.id, TaskState.PLANNING)
    queue.append(task.id, "plan.drafted", {"scenario_ids": ["a"]})
    stored = queue.load(task.id)
    assert stored.state is TaskState.PLANNING
    assert stored.attempts == 1
    assert project(queue.events(task.id)) == stored
    assert queue.verify_projection(task.id) == stored


def test_invalid_transition_writes_nothing(paths: WorksPaths) -> None:
    queue = new_queue(paths)
    task = submit(queue)
    before = (paths.task_dir(task.id) / EVENTS_FILE).read_text(encoding="utf-8")
    with pytest.raises(StateError):
        queue.transition(task.id, TaskState.RELEASED)
    after = (paths.task_dir(task.id) / EVENTS_FILE).read_text(encoding="utf-8")
    assert before == after


def test_unknown_event_type_is_refused(paths: WorksPaths) -> None:
    queue = new_queue(paths)
    task = submit(queue)
    with pytest.raises(StateError):
        queue.append(task.id, "made.up", {})


def test_event_sequence_is_monotonic(paths: WorksPaths) -> None:
    queue = new_queue(paths)
    task = submit(queue)
    queue.append(task.id, "note", {"message": "one"})
    queue.append(task.id, "note", {"message": "two"})
    assert [event.seq for event in queue.events(task.id)] == [1, 2, 3]


def test_two_supervisors_cannot_own_one_task(paths: WorksPaths) -> None:
    queue = new_queue(paths)
    task = submit(queue)
    queue.claim(task.id, "owner-a")
    queue.claim(task.id, "owner-a")
    with pytest.raises(ConflictError):
        queue.claim(task.id, "owner-b")
    assert queue.owner(task.id) == "owner-a"
    queue.release(task.id, "owner-b")
    assert queue.owner(task.id) == "owner-a"
    queue.release(task.id, "owner-a")
    assert queue.owner(task.id) is None


def test_missing_task_is_not_found(paths: WorksPaths) -> None:
    queue = new_queue(paths)
    with pytest.raises(NotFoundError):
        queue.load("t-missing")
    with pytest.raises(NotFoundError):
        queue.events("t-missing")
    with pytest.raises(NotFoundError):
        queue.append("t-missing", "note", {})


def test_a_missing_projection_is_rebuilt_from_events(paths: WorksPaths) -> None:
    queue = new_queue(paths)
    task = submit(queue)
    queue.transition(task.id, TaskState.REPRODUCING)
    (paths.task_dir(task.id) / "task.yaml").unlink()
    restored = queue.load(task.id)
    assert restored.state is TaskState.REPRODUCING
    assert queue.verify_projection(task.id) == restored


def test_budget_and_scope_round_trip(paths: WorksPaths) -> None:
    queue = new_queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.TRACKER, ref="42"),
        flow="fix-issue",
        product="openjiuwen",
        repo=".",
        budget=Budget(tokens=10, usd=0.5),
    )
    loaded = queue.load(task.id)
    assert loaded.budget.tokens == 10
    assert loaded.budget.usd == 0.5


def test_events_file_is_jsonl(paths: WorksPaths) -> None:
    queue = new_queue(paths)
    task = submit(queue)
    lines = (paths.task_dir(task.id) / EVENTS_FILE).read_text(encoding="utf-8").splitlines()
    assert lines
    for line in lines:
        assert json.loads(line)["schema_version"] == 1
