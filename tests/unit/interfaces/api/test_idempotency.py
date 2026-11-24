from __future__ import annotations

from fastapi.testclient import TestClient

from works.adapters.queue.store import Queue
from works.domain.records import Source, SourceKind
from works.interfaces.api.app import create_app

BASE = "http://127.0.0.1"


def make(paths):
    app = create_app(paths, writable=True, bootstrap_token="bootstrap")  # noqa: S106 - test fixture
    return TestClient(app, base_url=BASE), app


def task(paths) -> str:
    item, _ = Queue(paths).submit(
        source=Source(kind=SourceKind.MANUAL, ref="IDEMP-1", title="idempotent"),
        flow="fix-issue",
        product="Fixture",
        repo=".",
    )
    return item.id


def test_a_replayed_action_returns_the_same_response_once(paths) -> None:
    client, app = make(paths)
    task_id = task(paths)
    body = {"action": "add-context", "task_id": task_id, "message": "once"}
    with client:
        headers = {
            "Authorization": f"Bearer {app.state.works.security.token}",
            "Idempotency-Key": "action-key-1",
        }
        first = client.post("/api/v1/actions", headers=headers, json=body)
        assert first.status_code == 200, first.text
        second = client.post("/api/v1/actions", headers=headers, json=body)
    assert second.status_code == 200
    assert second.json() == first.json()
    assert second.headers["x-idempotent-replay"] == "true"
    notes = [event for event in Queue(paths).events(task_id) if event.type == "thread.note"]
    assert len(notes) == 1


def test_the_same_key_with_a_different_body_is_a_conflict(paths) -> None:
    client, app = make(paths)
    task_id = task(paths)
    with client:
        headers = {
            "Authorization": f"Bearer {app.state.works.security.token}",
            "Idempotency-Key": "action-key-2",
        }
        assert (
            client.post(
                "/api/v1/actions",
                headers=headers,
                json={"action": "add-context", "task_id": task_id, "message": "one"},
            ).status_code
            == 200
        )
        changed = client.post(
            "/api/v1/actions",
            headers=headers,
            json={"action": "add-context", "task_id": task_id, "message": "two"},
        )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "conflict"


def test_create_task_replay_keeps_one_task(paths, repo) -> None:
    client, app = make(paths)
    body = {
        "repo": str(repo.path),
        "product": "Fixture",
        "ref": "IDEMP-TASK-1",
        "title": "Only once",
    }
    with client:
        headers = {
            "Authorization": f"Bearer {app.state.works.security.token}",
            "Idempotency-Key": "task-key-1",
        }
        first = client.post("/api/v1/tasks", headers=headers, json=body)
        second = client.post("/api/v1/tasks", headers=headers, json=body)
    assert first.status_code == 201, first.text
    assert second.status_code == 201
    assert second.json()["task"]["id"] == first.json()["task"]["id"]
    assert (
        len([item for item in Queue(paths).list_tasks() if item.source.ref == "IDEMP-TASK-1"]) == 1
    )
