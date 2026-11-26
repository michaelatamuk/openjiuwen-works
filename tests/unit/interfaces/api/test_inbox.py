from __future__ import annotations

from works.adapters.queue.store import Queue
from works.domain.records import Source, SourceKind, TaskState
from works.interfaces.api.routes.inbox import _dismissed, _remember_dismissal, groups


def _task(paths, ref: str, title: str) -> str:
    task, _created = Queue(paths).submit(
        source=Source(kind=SourceKind.TRACKER, ref=ref, title=title, channel="github"),
        flow="fix-issue",
        product="P",
        repo=str(paths.root / "repo"),
    )
    return task.id


def test_a_title_group_carries_its_members_and_signature(paths) -> None:
    first = _task(paths, "GH-1", "Add subtracts")
    second = _task(paths, "GH-2", "add SUBTRACTS!")

    found = groups(Queue(paths).list_tasks())

    assert len(found) == 1
    assert found[0]["reason"]
    assert found[0]["signature"]
    assert [item["id"] for item in found[0]["tasks"]] == [first, second]
    assert all("created_at" in item for item in found[0]["tasks"])


def test_a_terminal_task_leaves_the_group(paths) -> None:
    first = _task(paths, "GH-1", "Add subtracts")
    _task(paths, "GH-2", "Add subtracts")
    queue = Queue(paths)
    queue.transition(first, TaskState.REPRODUCING)
    queue.transition(first, TaskState.BLOCKED)

    assert groups(queue.list_tasks()) == []


def test_a_dismissal_is_remembered(paths) -> None:
    _remember_dismissal(paths, "sig-1")
    _remember_dismissal(paths, "sig-2")

    assert _dismissed(paths) == {"sig-1", "sig-2"}
