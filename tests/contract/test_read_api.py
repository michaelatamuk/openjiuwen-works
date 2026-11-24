from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from tests.contract.canonicalize import canonicalize

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BASE = "/api/v1"


def fixture(name: str) -> object:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def canon(payload: object, home: Path) -> object:
    return canonicalize(payload, home=home, repo=home / "repo")


def slug(ref: str) -> str:
    raw = "".join(character if character.isalnum() else "-" for character in ref.lower())
    return raw.strip("-")


def stable_health(payload: dict[str, object]) -> dict[str, object]:
    return {
        "ok": payload.get("ok"),
        "readonly": payload.get("readonly"),
        "write": payload.get("write"),
        "root": payload.get("root"),
        "version": payload.get("version"),
        "has_ai": isinstance(payload.get("ai"), dict),
        "has_builder": isinstance(payload.get("builder"), dict),
    }


def test_health_matches_the_recorded_subset(client: TestClient, seeded_home: Path) -> None:
    body = client.get(f"{BASE}/health").json()
    assert canon(stable_health(body), seeded_home) == fixture("health")


def test_task_list_matches(client: TestClient, seeded_home: Path) -> None:
    response = client.get(f"{BASE}/tasks", params={"limit": 200})
    assert response.status_code == 200
    assert canon(response.json(), seeded_home) == fixture("tasks")


def test_every_task_detail_and_run_list_matches(client: TestClient, seeded_home: Path) -> None:
    tasks = client.get(f"{BASE}/tasks", params={"limit": 200}).json()["tasks"]
    for task in tasks:
        name = slug(str(task["source"]).split(":", 1)[-1])
        detail = client.get(f"{BASE}/tasks/{task['id']}")
        assert detail.status_code == 200, name
        assert canon(detail.json(), seeded_home) == fixture(f"task-{name}"), name

        runs = client.get(f"{BASE}/tasks/{task['id']}/runs")
        assert runs.status_code == 200, name
        assert canon(runs.json(), seeded_home) == fixture(f"runs-{name}"), name


def test_maps_metrics_and_ledger_match(client: TestClient, seeded_home: Path) -> None:
    for path, name in (
        ("/products", "products"),
        ("/detectors", "detectors"),
        ("/metrics", "metrics"),
        ("/ledger", "ledger"),
    ):
        response = client.get(f"{BASE}{path}")
        assert response.status_code == 200, path
        assert canon(response.json(), seeded_home) == fixture(name), path


def test_export_download_and_traversal(client: TestClient) -> None:
    tasks = client.get(f"{BASE}/tasks", params={"limit": 200}).json()["tasks"]
    released = next(task for task in tasks if task["state"] == "released")
    response = client.get(f"{BASE}/tasks/{released['id']}/export/evidence.json")
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["content-type"].startswith("application/json")

    missing = client.get(f"{BASE}/tasks/{released['id']}/export/nope.json")
    assert missing.status_code == 404

    traversal = client.get(f"{BASE}/tasks/{released['id']}/artifacts/../../../run.json")
    assert traversal.status_code == 404


def test_artifact_urls_are_versioned_and_fetchable(client: TestClient) -> None:
    tasks = client.get(f"{BASE}/tasks", params={"limit": 200}).json()["tasks"]
    proved = next(task for task in tasks if task["state"] == "proved")
    detail = client.get(f"{BASE}/tasks/{proved['id']}").json()
    artifacts = detail["artifacts"]
    assert artifacts
    url = artifacts[0]["url"]
    assert url.startswith("/api/v1/tasks/")
    response = client.get(url)
    assert response.status_code == 200
    assert response.content
