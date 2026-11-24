from __future__ import annotations

from works.adapters.queue.index import TaskIndex
from works.adapters.queue.store import Queue
from works.domain.records import Source, SourceKind, TaskState
from works.interfaces.api import read
from works.interfaces.api.presenters.tasks.detail import _task_summary


def test_the_index_page_matches_the_file_scan(paths) -> None:
    queue = Queue(paths)
    ids: list[str] = []
    for index in range(5):
        task, _ = queue.submit(
            source=Source(kind=SourceKind.MANUAL, ref=f"PARITY-{index}", title=f"Parity {index}"),
            flow="fix-issue",
            product="Fixture",
            repo=".",
        )
        ids.append(task.id)
        queue.transition(task.id, TaskState.REPRODUCING)
        queue.append(task.id, "risk.rated", {"level": "medium", "reasons": ["parity"]})
        queue.append(task.id, "decision.made", {"verb": "act", "reason_code": "parity"})
        queue.append(task.id, "would_block", {"reason": "parity"})

    indexed = read.tasks(paths, limit=50)[1]["tasks"]
    scanned = [_task_summary(queue.load(task_id), queue.events(task_id)) for task_id in ids]
    scanned.sort(key=lambda item: str(item["updated_at"]), reverse=True)
    assert indexed == scanned

    recent = TaskIndex(paths.queue / "index.sqlite3").list_recent(2)
    assert [item["id"] for item in recent] == [item["id"] for item in indexed[:2]]
