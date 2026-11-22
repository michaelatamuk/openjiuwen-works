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
def running(paths, *, write: bool = False) -> Iterator[str]:
    server = serve(paths, host="127.0.0.1", port=0, write=write)
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


def post(base: str, path: str, payload: dict, *, header: bool = True) -> tuple[int, str]:
    headers = {"Content-Type": "application/json"}
    if header:
        headers["X-Works-Write"] = "1"
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def test_static_page_and_assets(paths) -> None:
    with running(paths) as base:
        status, body = get(base, "/")
        assert status == 200
        assert "openJiuwen Works" in body
        assert "LOCAL PREVIEW" in body
        assert "Nothing selected" not in body
        assert "Start with a report" in body
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


def test_report_intake_is_refused_in_read_only(paths, repo) -> None:
    with running(paths) as base:
        status, body = post(
            base,
            "/api/tasks",
            {"repo": str(repo.path), "ref": "BUG-1", "title": "It broke"},
        )
        assert status == 405
        assert "read-only" in json.loads(body)["error"]


def test_report_intake_creates_only_a_queued_task(paths, repo) -> None:
    payload = {
        "repo": str(repo.path),
        "product": "Blender",
        "ref": "BLENDER-1",
        "title": "The preview flickers",
    }
    with running(paths, write=True) as base:
        status, health = get(base, "/api/health")
        assert status == 200
        assert json.loads(health)["write"] is True

        status, body = post(base, "/api/tasks", payload)
        assert status == 201, body
        created = json.loads(body)
        assert created["created"] is True
        assert created["task"]["state"] == "queued"
        assert created["task"]["product"] == "Blender"

        status, body = post(base, "/api/tasks", payload)
        assert status == 200
        assert json.loads(body)["created"] is False


def test_report_requires_the_write_header_and_a_repository(paths, repo) -> None:
    with running(paths, write=True) as base:
        status, _ = post(
            base,
            "/api/tasks",
            {"repo": str(repo.path), "ref": "BUG-1", "title": "It broke"},
            header=False,
        )
        assert status == 403
        status, body = post(
            base,
            "/api/tasks",
            {"repo": str(paths.root / "absent"), "ref": "BUG-1", "title": "It broke"},
        )
        assert status == 400
        assert "does not exist" in json.loads(body)["error"]


def test_readiness_runs_only_in_write_mode(paths, repo) -> None:
    with running(paths, write=True) as base:
        status, body = post(base, "/api/readiness", {"repo": str(repo.path)})
        assert status == 200, body
        report = json.loads(body)
        assert report["status"] == "fail"
        assert report["checks"]
    with running(paths) as base:
        status, _ = post(base, "/api/readiness", {"repo": str(repo.path)})
        assert status == 405


def test_a_run_artifact_is_served_and_traversal_is_refused(paths, submit) -> None:
    task = submit()
    run_dir = paths.runs / "r-artifact"
    (run_dir / "artifacts").mkdir(parents=True)
    (run_dir / "artifacts" / "story.png").write_bytes(b"\x89PNG\r\n")
    (run_dir / "run.json").write_text(
        json.dumps({"task_id": task.id, "finished_at": "2026-11-21T22:00:00Z"}),
        encoding="utf-8",
    )
    with running(paths) as base:
        with urlopen(f"{base}/api/tasks/{task.id}/artifacts/story.png", timeout=10) as response:
            assert response.status == 200
            assert response.read() == b"\x89PNG\r\n"
            assert response.headers["Content-Type"] == "image/png"
        try:
            urlopen(f"{base}/api/tasks/{task.id}/artifacts/%2e%2e%2fsecret", timeout=10)
        except HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("path traversal must be refused")
        status, _ = get(base, f"/api/tasks/{task.id}/artifacts/absent.png")
        assert status == 404
        status, _ = get(base, "/api/tasks/t-absent/artifacts/story.png")
        assert status == 404


def test_write_endpoint_rejects_unknown_path_bad_json_and_non_object(paths, repo) -> None:
    with running(paths, write=True) as base:
        status, _ = post(base, "/api/unknown", {"repo": str(repo.path)})
        assert status == 404
        request = Request(
            f"{base}/api/tasks",
            data=b"{",
            headers={"Content-Type": "application/json", "X-Works-Write": "1"},
            method="POST",
        )
        try:
            urlopen(request, timeout=10)
        except HTTPError as exc:
            assert exc.code == 400
        else:
            raise AssertionError("invalid JSON must be refused")
        status, _ = post(base, "/api/tasks", ["not", "an", "object"])
        assert status == 400


def test_write_endpoint_rejects_a_non_git_repo_and_unknown_kind(paths, tmp_path, repo) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with running(paths, write=True) as base:
        status, body = post(
            base,
            "/api/tasks",
            {"repo": str(plain), "ref": "BUG-1", "title": "It broke"},
        )
        assert status == 400
        assert "not a git repository" in json.loads(body)["error"]
        status, body = post(
            base,
            "/api/tasks",
            {"repo": str(repo.path), "ref": "BUG-1", "title": "It broke", "kind": "pigeon"},
        )
        assert status == 400
        status, _ = post(
            base,
            "/api/tasks",
            {"repo": str(repo.path), "ref": "", "title": ""},
        )
        assert status == 400
        status, _ = post(base, "/api/readiness", {})
        assert status == 400
