from __future__ import annotations

from works import fast
from works.config import WorksPaths
from works.index import TaskIndex
from works.queue import INDEX_FILE, TASK_JSON, Queue
from works.records import Source, SourceKind, TaskState


def submit(queue: Queue, ref: str = "GH-1") -> str:
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref=ref, title="a bug"),
        flow="fix-issue",
        product="openjiuwen",
        repo=".",
    )
    return task.id


def test_submit_writes_both_projections_and_the_index(paths: WorksPaths) -> None:
    queue = Queue(paths)
    task_id = submit(queue)
    assert (paths.task_dir(task_id) / TASK_JSON).exists()
    assert (paths.queue / INDEX_FILE).exists()
    listed = fast.summaries(paths.queue)
    assert listed is not None
    assert [item["id"] for item in listed] == [task_id]
    assert fast.summary(paths.queue, task_id)["state"] == "queued"


def test_transitions_update_the_index(paths: WorksPaths) -> None:
    queue = Queue(paths)
    task_id = submit(queue)
    queue.transition(task_id, TaskState.REPRODUCING)
    assert fast.summary(paths.queue, task_id)["state"] == "reproducing"


def test_an_empty_queue_is_an_empty_list_not_a_fallback(paths: WorksPaths) -> None:
    assert fast.summaries(paths.queue) == []


def test_a_missing_index_can_be_rebuilt(paths: WorksPaths) -> None:
    queue = Queue(paths)
    task_id = submit(queue)
    (paths.queue / INDEX_FILE).unlink()
    assert fast.summaries(paths.queue) is None
    rebuilt = queue.rebuild_index()
    assert [item["id"] for item in rebuilt] == [task_id]
    assert fast.summaries(paths.queue) is not None


def test_the_index_survives_a_corrupt_file(paths: WorksPaths) -> None:
    queue = Queue(paths)
    task_id = submit(queue)
    (paths.queue / INDEX_FILE).write_text("not a database", encoding="utf-8")
    assert fast.summaries(paths.queue) is None
    assert [item["id"] for item in queue.rebuild_index()] == [task_id]
    assert fast.summaries(paths.queue) is not None


def test_event_count_is_cheap_and_correct(paths: WorksPaths) -> None:
    queue = Queue(paths)
    task_id = submit(queue)
    queue.append(task_id, "note", {"message": "one"})
    assert fast.event_count(paths.queue, task_id) == 2
    assert fast.event_count(paths.queue, "t-absent") == 0


def test_owner_is_read_without_loading_the_task(paths: WorksPaths) -> None:
    queue = Queue(paths)
    task_id = submit(queue)
    queue.claim(task_id, "r-1")
    assert fast.owner(paths.queue, task_id) == "r-1"
    queue.release(task_id, "r-1")
    assert fast.owner(paths.queue, task_id) is None


def test_the_index_is_a_derived_sqlite_table(paths: WorksPaths) -> None:
    task_id = submit(Queue(paths))
    index = TaskIndex(paths.queue / INDEX_FILE)
    assert index.count() == 1
    assert index.get(task_id) is not None
    assert index.list()[0]["state"] == "queued"
