from __future__ import annotations

from works.adapters.queue.store import Queue
from works.config import WorksPaths
from works.domain.records import Finding, Source, SourceKind


def test_a_finding_is_an_event_and_survives_replay(paths: WorksPaths) -> None:
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="GH-1"),
        flow="fix-issue",
        product="openjiuwen",
        repo=".",
    )
    finding = Finding(
        step="build",
        summary="add returned a difference",
        confidence=0.9,
        uncertainty="none observed",
        evidence=["calc/core.py:5"],
    )
    queue.append(task.id, "finding", finding.model_dump(mode="json"))
    events = queue.events(task.id)
    assert events[-1].type == "finding"
    assert Finding.model_validate(events[-1].data) == finding
    queue.verify_projection(task.id)
