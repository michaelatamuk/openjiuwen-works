"""Thread message handlers: the report itself."""

from __future__ import annotations

from works.domain.records import Event, Task
from works.interfaces.api.presenters.thread.messages.types import Fields


def _created(event: Event, task: Task) -> Fields:
    role = {
        "manual": "person",
        "tracker": "tracker",
        "detector": "monitor",
    }.get(task.source.kind.value, "person")
    return {
        "role": role,
        "title": "Reported",
        "body": task.source.title,
        "facts": [f"{task.source.kind.value}:{task.source.ref}", task.product],
    }
