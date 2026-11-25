from __future__ import annotations

from fastapi.testclient import TestClient

from works.adapters.queue.store import Queue
from works.interfaces.api.app import create_app


def test_a_task_can_name_a_remote_and_override_the_command(paths) -> None:
    app = create_app(paths, writable=True, bootstrap_token="bootstrap")  # noqa: S106

    with TestClient(app, base_url="http://127.0.0.1") as client:
        token = client.app.state.works.security.token
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/api/v1/tasks",
            json={
                "ref": "M12-1",
                "title": "remote task",
                "kind": "manual",
                "product": "openjiuwen",
                "repo_url": "https://example.invalid/o/r.git",
                "repo_ref": "main",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["task"]["id"]
        task = Queue(paths).load(task_id)
        assert task.repo_url == "https://example.invalid/o/r.git"
        assert task.repo_ref == "main"

        override = client.post(
            f"/api/v1/tasks/{task_id}/reproduction",
            json={"command": "python -m pytest tests/test_core.py -q"},
            headers=headers,
        )
        assert override.status_code == 200, override.text

    stored = Queue(paths).load(task_id)
    assert stored.reproduction_command[-2:] == ["tests/test_core.py", "-q"]
    assert stored.reproduction_source == "person"
