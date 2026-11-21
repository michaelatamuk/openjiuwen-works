from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from works.ui.server import serve


@contextmanager
def running(paths) -> Iterator[str]:
    server = serve(paths, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def get(base: str, path: str) -> tuple[int, str]:
    try:
        with urlopen(f"{base}{path}", timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def test_static_page_and_assets(paths) -> None:
    with running(paths) as base:
        status, body = get(base, "/")
        assert status == 200
        assert "openJiuwen Works" in body
        assert "LOCAL PREVIEW" in body
        status, script = get(base, "/app.js")
        assert status == 200
        assert "boot()" in script
        status, mascot = get(base, "/mira.svg")
        assert status == 200
        assert "<svg" in mascot


def test_health_is_read_only(paths) -> None:
    with running(paths) as base:
        status, body = get(base, "/api/health")
        assert status == 200
        assert json.loads(body)["readonly"] is True
        request = Request(f"{base}/api/tasks", method="POST")
        with pytest.raises(HTTPError) as exc:
            urlopen(request, timeout=10)
        assert exc.value.code == 405


def test_tasks_are_listed(paths, submit) -> None:
    task = submit()
    with running(paths) as base:
        status, body = get(base, "/api/tasks")
        assert status == 200
        tasks = json.loads(body)["tasks"]
        assert tasks[0]["id"] == task.id
        assert tasks[0]["state"] == "queued"


def test_task_detail_includes_readiness_and_timeline(paths, submit) -> None:
    task = submit()
    with running(paths) as base:
        status, body = get(base, f"/api/tasks/{task.id}")
        assert status == 200
        detail = json.loads(body)
        assert detail["task"]["id"] == task.id
        assert detail["readiness"]["available"] is True
        assert detail["features"]["available"] is False
        assert detail["timeline"][0]["type"] == "task.created"
        assert detail["pipeline"]["story"][0]["label"] == "Reported"
        assert [item["label"] for item in detail["pipeline"]["story"]] == [
            "Reported",
            "Picked up",
            "Confirmed",
            "Fixed",
            "Checked",
            "Deliver to openjiuwen",
        ]
        assert len(detail["pipeline"]["technical"]) == 10
        assert detail["pipeline"]["replay"]


def test_task_detail_includes_a_run_and_evidence(paths, submit) -> None:
    task = submit()
    run_dir = paths.runs / "r-test"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "r-test",
                "task_id": task.id,
                "flow": "fix-issue",
                "state": "proved",
                "stop_reason": "completed",
                "started_at": "2026-11-21T10:00:00Z",
                "finished_at": "2026-11-21T10:01:00Z",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "evidence.json").write_text(
        json.dumps(
            {
                "run_id": "r-test",
                "task_id": task.id,
                "flow": "fix-issue",
                "product": "openjiuwen",
                "source": "manual:GH-1",
                "state": "proved",
                "stop_reason": "completed",
                "verdict": {"allow": True, "reason": "all P0 passed", "outcomes": []},
                "risk": {"level": "low", "reasons": ["docs only"], "owners": []},
                "decision": {
                    "verb": "act",
                    "action": "allow",
                    "reason_code": "evidence_sufficient",
                },
                "tokens": 1200,
                "usd": 0.012,
                "duration_ms": 1000,
            }
        ),
        encoding="utf-8",
    )
    with running(paths) as base:
        status, body = get(base, f"/api/tasks/{task.id}")
        assert status == 200
        detail = json.loads(body)
        assert detail["run"]["run_id"] == "r-test"
        assert detail["evidence"]["risk"]["level"] == "low"
        assert detail["evidence"]["decision"]["verb"] == "act"


def test_unknown_task_is_a_404(paths) -> None:
    with running(paths) as base:
        status, body = get(base, "/api/tasks/t-absent")
        assert status == 404
        assert "error" in json.loads(body)
