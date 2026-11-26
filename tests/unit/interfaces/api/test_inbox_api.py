from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

BASE = "/api/v1"


def wait_job(client: TestClient, job_id: str, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"{BASE}/jobs/{job_id}").json()
        if body["status"] in ("succeeded", "failed", "cancelled"):
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish")


def test_inbox_lists_groups(seeded_client: TestClient) -> None:
    response = seeded_client.get(f"{BASE}/inbox")

    assert response.status_code == 200
    body = response.json()
    assert "duplicates" in body
    assert "gates" in body


def test_merge_rejects_itself(seeded_client: TestClient, auth: dict[str, str]) -> None:
    tasks = seeded_client.get(f"{BASE}/tasks").json()["tasks"]
    queued = next(task for task in tasks if task["state"] == "queued")

    response = seeded_client.post(
        f"{BASE}/tasks/{queued['id']}/merge", headers=auth, json={"into": queued["id"]}
    )

    assert response.status_code == 400


def test_merge_blocks_the_duplicate(seeded_client: TestClient, auth: dict[str, str]) -> None:
    tasks = seeded_client.get(f"{BASE}/tasks").json()["tasks"]
    queued = next(task for task in tasks if task["state"] == "queued")
    proved = next(task for task in tasks if task["state"] == "proved")

    response = seeded_client.post(
        f"{BASE}/tasks/{queued['id']}/merge", headers=auth, json={"into": proved["id"]}
    )

    assert response.status_code == 200
    assert response.json()["merged"] == queued["id"]
    after = seeded_client.get(f"{BASE}/tasks/{queued['id']}").json()
    assert after["task"]["state"] == "blocked"


def test_dismiss_remembers_a_signature(seeded_client: TestClient, auth: dict[str, str]) -> None:
    response = seeded_client.post(
        f"{BASE}/inbox/dismiss", headers=auth, json={"signature": "sig-test"}
    )

    assert response.status_code == 200
    assert response.json()["signature"] == "sig-test"


def test_dismiss_requires_a_signature(seeded_client: TestClient, auth: dict[str, str]) -> None:
    response = seeded_client.post(f"{BASE}/inbox/dismiss", headers=auth, json={"signature": " "})

    assert response.status_code == 400


def test_sources_route_runs_a_job(
    seeded_client: TestClient, auth: dict[str, str], monkeypatch
) -> None:
    from works.interfaces.api import write

    def fake(paths: object, payload: dict[str, Any], lock: object) -> tuple[int, dict[str, Any]]:
        return 200, {"ok": True, "source": "github", "tasks": []}

    monkeypatch.setattr(write, "run_source", fake)
    accepted = seeded_client.post(
        f"{BASE}/sources",
        headers=auth,
        json={
            "source": "github",
            "product": "Fixture",
            "repository": "o/r",
            "dispatch_on_import": True,
        },
    )

    assert accepted.status_code == 202
    job = wait_job(seeded_client, accepted.json()["job"]["id"])
    assert job["status"] == "succeeded"
    assert job["result"]["tasks"] == []
