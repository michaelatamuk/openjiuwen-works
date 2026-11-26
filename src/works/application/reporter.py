"""A reporter's reply can reopen a released task — with context, once per comment.

The loop is deliberately small: match the comment to the task it came from, record it as an event,
and move a released task back to the queue. It never bypasses the scheduler or a gate, and it never
guesses which task a comment belongs to.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from works.adapters.queue.store import Queue
from works.application.delivery.release import _latest_run
from works.config.paths import WorksPaths
from works.domain.records import Event, Task, TaskState

REPLY_EVENT = "reporter.replied"
MAX_REOPENS_PER_DAY = 3
BOT_SUFFIXES = ("[bot]",)


@dataclass(frozen=True)
class Reply:
    task_id: str | None
    reopened: bool
    reason: str
    replies_today: int = 0
    previous_run: str | None = None


def _is_bot(login: str, kind: str) -> bool:
    if kind.lower() == "bot":
        return True
    return login.lower().endswith(BOT_SUFFIXES)


def _replies(events: list[Event]) -> list[Event]:
    return [event for event in events if event.type == REPLY_EVENT]


def reply_texts(events: list[Event], *, limit: int = 3) -> tuple[str, ...]:
    """The last reporter notes, for the planner's bounded context."""
    texts = [str(event.data.get("text") or "").strip() for event in _replies(events)]
    return tuple(text for text in texts if text)[-limit:]


def _previous_run(paths: WorksPaths, task_id: str) -> tuple[str | None, str | None]:
    run_dir = _latest_run(paths, task_id)
    if run_dir is None:
        return None, None
    proof = None
    evidence_path = run_dir / "evidence.json"
    if evidence_path.is_file():
        try:
            proof = json.loads(evidence_path.read_text(encoding="utf-8")).get("proof_sha256")
        except (OSError, ValueError):
            proof = None
    return run_dir.name, proof if isinstance(proof, str) else None


def find_task(queue: Queue, *, ref: str | None = None, url: str | None = None) -> Task | None:
    """The most recent task whose source matches this comment, or None."""
    if not ref and not url:
        return None
    candidates = sorted(
        (path for path in queue.paths.queue.glob("t-*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:200]
    for directory in candidates:
        try:
            task = queue.load(directory.name)
        except (OSError, ValueError):
            continue
        if ref and task.source.ref == ref:
            return task
        if url and url in task.source.links:
            return task
    return None


def record_reply(
    paths: WorksPaths,
    *,
    text: str,
    author: str,
    source: str,
    event_id: str | None = None,
    task_id: str | None = None,
    ref: str | None = None,
    url: str | None = None,
    closed: bool = False,
    author_kind: str = "User",
    queue: Queue | None = None,
) -> Reply:
    queue = queue or Queue(paths)
    body = " ".join(text.split())
    if not body:
        return Reply(task_id=None, reopened=False, reason="empty")
    if _is_bot(author, author_kind):
        return Reply(task_id=None, reopened=False, reason="bot")

    task = queue.load(task_id) if task_id else find_task(queue, ref=ref, url=url)
    if task is None:
        return Reply(task_id=None, reopened=False, reason="no_task")

    events = queue.events(task.id)
    if event_id and any(event.data.get("event_id") == event_id for event in _replies(events)):
        return Reply(task_id=task.id, reopened=False, reason="duplicate")

    cutoff = datetime.now(tz=UTC) - timedelta(hours=24)
    today = len([event for event in _replies(events) if event.ts >= cutoff])
    if today >= MAX_REOPENS_PER_DAY:
        return Reply(task_id=task.id, reopened=False, reason="limit", replies_today=today)

    previous_run, previous_proof = _previous_run(paths, task.id)
    reopened = task.state is TaskState.RELEASED and not closed
    queue.append(
        task.id,
        REPLY_EVENT,
        {
            "text": body,
            "author": author,
            "source": source,
            "event_id": event_id,
            "url": url,
            "closed": closed,
            "reopened": reopened,
            "previous_run": previous_run,
            "previous_proof": previous_proof,
        },
    )
    if reopened:
        queue.transition(task.id, TaskState.QUEUED, reason="reporter_replied")
        return Reply(
            task_id=task.id,
            reopened=True,
            reason="reopened",
            replies_today=today + 1,
            previous_run=previous_run,
        )
    reason = "closed" if closed else "not_released"
    return Reply(
        task_id=task.id,
        reopened=False,
        reason=reason,
        replies_today=today + 1,
        previous_run=previous_run,
    )
