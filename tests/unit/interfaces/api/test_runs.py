from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from works.adapters.queue.store import Queue
from works.domain.records import Source, SourceKind
from works.interfaces.api.app import create_app

BASE = "http://127.0.0.1"


def wait_job(client: TestClient, job_id: str, timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/v1/jobs/{job_id}").json()
        if body["status"] in ("succeeded", "failed", "cancelled"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


def make_task(paths, repo, ref: str) -> str:
    task, _ = Queue(paths).submit(
        source=Source(kind=SourceKind.MANUAL, ref=ref, title=f"Run {ref}"),
        flow="fix-issue",
        product="Fixture",
        repo=str(repo.path),
    )
    return task.id


def test_a_run_is_a_job_and_writes_a_record(paths, repo, factory_root) -> None:
    task_id = make_task(paths, repo, "RUN-1")
    app = create_app(paths, writable=True, bootstrap_token="bootstrap")  # noqa: S106 - test value
    scenarios = str(factory_root / "fixtures" / "scenarios" / "fix-add.yaml")
    trace = str(factory_root / "fixtures" / "traces" / "fix-add.json")
    with TestClient(app, base_url=BASE) as client:
        headers = {"Authorization": f"Bearer {app.state.works.security.token}"}
        response = client.post(
            "/api/v1/runs",
            headers=headers,
            json={
                "task_id": task_id,
                "approve_plan": True,
                "scenarios": scenarios,
                "trace": trace,
            },
        )
        assert response.status_code == 202, response.text
        job = wait_job(client, response.json()["job"]["id"])
        assert job["status"] == "succeeded", job
        record = job["result"]["run"]
        assert record["task_id"] == task_id
        assert record["state"] == "proved"

        run = client.get(f"/api/v1/runs/{record['run_id']}")
        assert run.status_code == 200
        assert run.json()["run_id"] == record["run_id"]


def test_dispatch_runs_the_queued_tasks(paths, repo, factory_root) -> None:
    first = make_task(paths, repo, "DISPATCH-1")
    second = make_task(paths, repo, "DISPATCH-2")
    app = create_app(paths, writable=True, bootstrap_token="bootstrap")  # noqa: S106 - test value
    scenarios = str(factory_root / "fixtures" / "scenarios" / "fix-add.yaml")
    trace = str(factory_root / "fixtures" / "traces" / "fix-add.json")
    with TestClient(app, base_url=BASE) as client:
        headers = {"Authorization": f"Bearer {app.state.works.security.token}"}
        response = client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={
                "limit": 5,
                "approve_plan": True,
                "scenarios": scenarios,
                "trace": trace,
            },
        )
        assert response.status_code == 202, response.text
        job = wait_job(client, response.json()["job"]["id"])
        assert job["status"] == "succeeded", job
        result = job["result"]
        assert result["selected"] == 2
        assert {item["task_id"] for item in result["runs"]} == {first, second}
        assert all("run" in item for item in result["runs"])
