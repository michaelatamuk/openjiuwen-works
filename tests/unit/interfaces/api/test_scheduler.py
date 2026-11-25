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


def test_scheduler_is_off_by_default(seeded_client: TestClient) -> None:
    body = seeded_client.get(f"{BASE}/scheduler").json()

    assert body["enabled"] is False
    assert body["paused"] is False
    assert body["limits"]["global"] == 2


def test_pause_and_resume_are_persisted(seeded_client: TestClient, auth: dict[str, str]) -> None:
    paused = seeded_client.post(
        f"{BASE}/scheduler/pause", headers=auth, json={"reason": "deploying"}
    )
    assert paused.status_code == 200
    assert paused.json()["paused"] is True
    assert seeded_client.get(f"{BASE}/scheduler").json()["paused"] is True

    resumed = seeded_client.post(f"{BASE}/scheduler/resume", headers=auth)
    assert resumed.status_code == 200
    assert seeded_client.get(f"{BASE}/scheduler").json()["paused"] is False


def test_pause_requires_a_token(seeded_client: TestClient) -> None:
    response = seeded_client.post(f"{BASE}/scheduler/pause", json={"reason": "x"})

    assert response.status_code == 401


def test_a_tick_is_a_job_and_claims_nothing_when_disabled(
    seeded_client: TestClient, auth: dict[str, str]
) -> None:
    accepted = seeded_client.post(f"{BASE}/scheduler/tick", headers=auth, json={"limit": 1})
    assert accepted.status_code == 202
    job = wait_job(seeded_client, accepted.json()["job"]["id"])

    assert job["status"] == "succeeded"
    assert job["result"]["status"] == "disabled"
    assert job["result"]["claimed"] == []
