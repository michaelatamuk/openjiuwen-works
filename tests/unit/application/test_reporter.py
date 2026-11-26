from __future__ import annotations

from works.adapters.queue.store import Queue
from works.application.reporter import MAX_REOPENS_PER_DAY, record_reply, reply_texts
from works.domain.records import Source, SourceKind, Task, TaskState

WORKFLOW = (
    TaskState.REPRODUCING,
    TaskState.REPRODUCED,
    TaskState.PLANNING,
    TaskState.PLAN_APPROVED,
    TaskState.BUILDING,
    TaskState.CHECKING,
    TaskState.PROVED,
    TaskState.RELEASING,
    TaskState.RELEASED,
)


def _released(paths, repo) -> Task:
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(
            kind=SourceKind.TRACKER,
            ref="o/r#7",
            title="add subtracts",
            links=["https://github.com/o/r/issues/7"],
        ),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(repo.path),
    )
    for state in WORKFLOW:
        queue.transition(task.id, state)
    return queue.load(task.id)


def test_a_reply_reopens_a_released_task(paths, repo) -> None:
    task = _released(paths, repo)

    reply = record_reply(
        paths,
        ref="o/r#7",
        text="still broken on Windows",
        author="michael",
        source="github",
        event_id="c-1",
    )

    assert reply.reopened is True
    assert reply.reason == "reopened"
    assert Queue(paths).load(task.id).state is TaskState.QUEUED
    event = Queue(paths).events(task.id)[-2]
    assert event.type == "reporter.replied"
    assert event.data["text"] == "still broken on Windows"


def test_a_reply_matches_the_task_by_url(paths, repo) -> None:
    task = _released(paths, repo)

    reply = record_reply(
        paths,
        url="https://github.com/o/r/issues/7",
        text="still failing",
        author="michael",
        source="github",
    )

    assert reply.task_id == task.id
    assert reply.reopened is True


def test_the_same_comment_is_recorded_once(paths, repo) -> None:
    _released(paths, repo)
    first = record_reply(
        paths, ref="o/r#7", text="still broken", author="michael", source="github", event_id="c-1"
    )
    second = record_reply(
        paths, ref="o/r#7", text="still broken", author="michael", source="github", event_id="c-1"
    )

    assert first.reopened is True
    assert second.reason == "duplicate"
    assert (
        len(
            [
                event
                for event in Queue(paths).events(first.task_id or "")
                if event.type == "reporter.replied"
            ]
        )
        == 1
    )


def test_a_closed_report_is_recorded_but_not_reopened(paths, repo) -> None:
    task = _released(paths, repo)

    reply = record_reply(
        paths,
        ref="o/r#7",
        text="same problem",
        author="michael",
        source="github",
        closed=True,
    )

    assert reply.reopened is False
    assert reply.reason == "closed"
    assert Queue(paths).load(task.id).state is TaskState.RELEASED
    assert any(event.type == "reporter.replied" for event in Queue(paths).events(task.id))


def test_a_bot_is_ignored(paths, repo) -> None:
    task = _released(paths, repo)

    reply = record_reply(
        paths,
        ref="o/r#7",
        text="+1",
        author="dependabot[bot]",
        source="github",
    )

    assert reply.reason == "bot"
    assert not any(event.type == "reporter.replied" for event in Queue(paths).events(task.id))


def test_an_unreleased_task_is_not_reopened(paths, repo) -> None:
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.TRACKER, ref="o/r#8", title="open"),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(repo.path),
    )

    reply = record_reply(paths, ref="o/r#8", text="any news?", author="michael", source="github")

    assert reply.reason == "not_released"
    assert Queue(paths).load(task.id).state is TaskState.QUEUED


def test_an_unknown_report_is_refused(paths, repo) -> None:
    reply = record_reply(paths, ref="o/r#404", text="hello", author="michael", source="github")

    assert reply.reason == "no_task"
    assert reply.task_id is None


def test_the_daily_limit_holds(paths, repo) -> None:
    task = _released(paths, repo)
    queue = Queue(paths)
    for index in range(MAX_REOPENS_PER_DAY):
        queue.append(
            task.id,
            "reporter.replied",
            {"text": f"still broken {index}", "author": "michael", "reopened": True},
        )

    reply = record_reply(paths, ref="o/r#7", text="one more", author="michael", source="github")

    assert reply.reason == "limit"
    assert reply.replies_today == MAX_REOPENS_PER_DAY


def test_reply_texts_feed_the_planner_with_the_last_three(paths, repo) -> None:
    task = _released(paths, repo)
    queue = Queue(paths)
    for index in range(4):
        queue.append(task.id, "reporter.replied", {"text": f"note {index}"})

    assert reply_texts(queue.events(task.id)) == ("note 1", "note 2", "note 3")
