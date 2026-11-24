from __future__ import annotations

import time
from http import HTTPStatus
from typing import Any

from fastapi.testclient import TestClient

BASE = "/api/v1"


def tasks_by_state(client: TestClient) -> dict[str, dict[str, Any]]:
    payload = client.get(f"{BASE}/tasks", params={"limit": 200}).json()
    return {task["state"]: task for task in payload["tasks"]}


def wait_job(client: TestClient, job_id: str, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"{BASE}/jobs/{job_id}").json()
        if body["status"] in ("succeeded", "failed", "cancelled"):
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish")


def test_write_actions_require_a_token(seeded_client: TestClient) -> None:
    response = seeded_client.post(
        f"{BASE}/actions", json={"action": "add-context", "task_id": "t-x", "message": "hi"}
    )
    assert response.status_code == 401


def test_add_context_is_synchronous(seeded_client: TestClient, auth: dict[str, str]) -> None:
    queued = tasks_by_state(seeded_client)["queued"]
    response = seeded_client.post(
        f"{BASE}/actions",
        headers=auth,
        json={"action": "add-context", "task_id": queued["id"], "message": "extra detail"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["event"]["type"] == "thread.note"


def test_approve_plan_is_synchronous(seeded_client: TestClient, auth: dict[str, str]) -> None:
    planning = tasks_by_state(seeded_client)["planning"]
    response = seeded_client.post(
        f"{BASE}/actions",
        headers=auth,
        json={"action": "approve-plan", "task_id": planning["id"]},
    )
    assert response.status_code == 200
    assert response.json()["task"]["state"] == "plan_approved"


def test_release_is_synchronous(seeded_client: TestClient, auth: dict[str, str]) -> None:
    proved = tasks_by_state(seeded_client)["proved"]
    response = seeded_client.post(
        f"{BASE}/actions",
        headers=auth,
        json={"action": "release", "task_id": proved["id"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["task"]["state"] == "proved" or body["task"]["state"] == "released"
    assert body["release"]["ready"] is True


def test_ask_is_rejected_with_a_stream_hint(
    seeded_client: TestClient, auth: dict[str, str]
) -> None:
    queued = tasks_by_state(seeded_client)["queued"]
    response = seeded_client.post(
        f"{BASE}/actions",
        headers=auth,
        json={"action": "ask", "task_id": queued["id"], "question": "why?"},
    )
    assert response.status_code == 400
    assert "ask/stream" in response.json()["error"]["message"]


def test_unknown_action_is_400(seeded_client: TestClient, auth: dict[str, str]) -> None:
    response = seeded_client.post(
        f"{BASE}/actions", headers=auth, json={"action": "made-up", "task_id": "t-x"}
    )
    assert response.status_code == 400


def test_team_verify_runs_as_a_job(
    seeded_client: TestClient, auth: dict[str, str], monkeypatch
) -> None:
    import works.application.team.launcher as launcher

    monkeypatch.setattr(launcher, "run_team_verify", lambda _paths, _task_id: {"verdict": "allow"})
    queued = tasks_by_state(seeded_client)["queued"]
    response = seeded_client.post(
        f"{BASE}/actions",
        headers=auth,
        json={"action": "team-verify", "task_id": queued["id"]},
    )
    assert response.status_code == 202
    job = wait_job(seeded_client, response.json()["job"]["id"])
    assert job["status"] == "succeeded"
    assert job["result"] == {"verdict": "allow"}


def test_readiness_runs_as_a_job(
    seeded_client: TestClient, auth: dict[str, str], seeded_home
) -> None:
    response = seeded_client.post(
        f"{BASE}/readiness",
        headers=auth,
        json={"repo": str(seeded_home / "repo")},
    )
    assert response.status_code == 202
    job = wait_job(seeded_client, response.json()["job"]["id"])
    assert job["status"] == "succeeded"
    assert "status" in job["result"]


def test_sources_run_as_a_job(seeded_client: TestClient, auth: dict[str, str], monkeypatch) -> None:
    import works.interfaces.api.write as write

    monkeypatch.setattr(
        write,
        "run_source",
        lambda _paths, _payload, _lock: (HTTPStatus.OK, {"ok": True, "created": 2}),
    )
    response = seeded_client.post(f"{BASE}/sources", headers=auth, json={"source": "github"})
    assert response.status_code == 202
    job = wait_job(seeded_client, response.json()["job"]["id"])
    assert job["status"] == "succeeded"
    assert job["result"]["created"] == 2


def test_settings_round_trip(seeded_client: TestClient, auth: dict[str, str]) -> None:
    current = seeded_client.get(f"{BASE}/settings/builder")
    assert current.status_code == 200
    assert current.json()["builder"]["runtime"] in ("openjiuwen", "swarm")

    saved = seeded_client.post(
        f"{BASE}/settings/builder",
        headers=auth,
        json={"runtime": "openjiuwen", "provider": "claudecode"},
    )
    assert saved.status_code == 200
    assert saved.json()["builder"]["runtime"] == "openjiuwen"
