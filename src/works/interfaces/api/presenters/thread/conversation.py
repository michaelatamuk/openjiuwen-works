"""The session conversation: every projectable event, in order."""

from __future__ import annotations

from typing import Any

from works.domain.records import Event, Task
from works.interfaces.api.presenters.thread.messages import _thread_message


def _thread(task: Task, events: list[Event]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for event in events:
        message = _thread_message(event, task)
        if message is not None:
            messages.append(message)
    return messages
