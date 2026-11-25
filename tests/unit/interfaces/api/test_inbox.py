from __future__ import annotations

from fastapi.testclient import TestClient

from works.adapters.queue.store import Queue
from works.domain.records import Source, SourceKind, TaskState
from works.interfaces.api.app import create_app
from works.interfaces.api.routes.inbox import groups, normalise


def _submit(paths, repo, ref: str, title: str):
    task, _ = Queue(paths).submit(
        source=Source(kind=SourceKind.MANUAL, ref=ref, title=title),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(repo.path),
    )
    return task


def test_normalise_collapses_punctuation() -> None:
    assert normalise("Add returns the  difference!") == "add returns the difference"


def test_the_same_title_is_a_duplicate_group(paths, repo) -> None:
    first = _submit(paths, repo, "A-1", "add returns the difference")
    second = _submit(paths, repo, "B-2", "Add returns the difference")
    _submit(paths, repo, "C-3", "something else entirely")

    found = groups(Queue(paths).list_tasks())

    assert len(found) == 1
    assert {item["id"] for item in found[0]["tasks"]} == {first.id, second.id}


def test_a_terminal_task_is_not_a_candidate(paths, repo) -> None:
    first = _submit(paths, repo, "A-1", "add returns the difference")
    second = _submit(paths, repo, "B-2", "add returns the difference")
    queue = Queue(paths)
    queue.transition(second.id, TaskState.BLOCKED)

    found = groups(queue.list_tasks())

    assert found == [], first.id


def test_merge_blocks_the_duplicate_and_records_it(paths, repo) -> None:
    first = _submit(paths, repo, "A-1", "add returns the difference")
    second = _submit(paths, repo, "B-2", "add returns the difference")
    app = create_app(paths, writable=True, bootstrap_token="bootstrap")  # noqa: S106

    with TestClient(app, base_url="http://127.0.0.1") as client:
        token = client.app.state.works.security.token
        response = client.post(
            f"/api/v1/tasks/{second.id}/merge",
            json={"into": first.id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200, response.text
    assert Queue(paths).load(second.id).state is TaskState.BLOCKED
    events = [event for event in Queue(paths).events(second.id) if event.type == "task.merged"]
    assert events and events[0].data["into"] == first.id


def test_mute_turns_a_source_off(paths) -> None:
    app = create_app(paths, writable=True, bootstrap_token="bootstrap")  # noqa: S106

    with TestClient(app, base_url="http://127.0.0.1") as client:
        token = client.app.state.works.security.token
        response = client.post(
            "/api/v1/inbox/mute",
            json={"source": "github"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["source"]["enabled"] is False


def test_the_inbox_lists_a_plan_waiting_for_a_person(paths, repo, monkeypatch) -> None:
    task = _submit(paths, repo, "GATE-INBOX", "a plan waits here")
    queue = Queue(paths)
    for state in (TaskState.REPRODUCING, TaskState.REPRODUCED, TaskState.PLANNING):
        queue.transition(task.id, state)
    queue.append(
        task.id,
        "plan.drafted",
        {
            "plan_id": f"p-{task.id}-v1",
            "hash": "a" * 64,
            "version": 1,
            "base_commit": "b" * 40,
            "checks_sha": "c" * 64,
        },
    )
    monkeypatch.setenv("WORKS_GATE_REMINDER_HOURS", "0")
    app = create_app(paths, writable=True, bootstrap_token="bootstrap")  # noqa: S106

    with TestClient(app, base_url="http://127.0.0.1") as client:
        body = client.get("/api/v1/inbox").json()

    assert body["gates"][0]["task_id"] == task.id
    assert body["gates"][0]["overdue"] is True
    assert body["gates"][0]["plan_version"] == 1
