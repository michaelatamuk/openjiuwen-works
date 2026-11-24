"""Smoke the action surface against a seeded home.

    python scripts/smoke_api.py
    python scripts/smoke_api.py --home %TEMP%\\opencode\\works-smoke --keep
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY))

from fastapi.testclient import TestClient  # noqa: E402

from scripts.seed_home import DEFAULT_NOW, seed  # noqa: E402
from works.interfaces.api.app import create_app  # noqa: E402

BASE = "/api/v1"


def wait_job(client: TestClient, job_id: str, timeout: float = 15.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"{BASE}/jobs/{job_id}").json()
        if body["status"] in ("succeeded", "failed", "cancelled"):
            return body
        time.sleep(0.05)
    raise SystemExit(f"job {job_id} did not finish")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=None)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    temporary = args.home is None
    home = args.home or Path(tempfile.mkdtemp(prefix="works-smoke-")) / "home"
    home = home.expanduser().resolve()
    if home.exists():
        shutil.rmtree(home)
    seed(home, now=DEFAULT_NOW)
    app = create_app(home, writable=True, bootstrap_token="smoke")
    try:
        with TestClient(app, base_url="http://127.0.0.1") as client:
            headers = {"Authorization": f"Bearer {app.state.works.security.token}"}
            tasks = client.get(f"{BASE}/tasks", params={"limit": 200}).json()["tasks"]
            by_state = {task["state"]: task for task in tasks}

            queued = by_state["queued"]
            response = client.post(
                f"{BASE}/actions",
                headers=headers,
                json={"action": "add-context", "task_id": queued["id"], "message": "smoke"},
            )
            assert response.status_code == 200, response.text

            planning = by_state["planning"]
            response = client.post(
                f"{BASE}/actions",
                headers=headers,
                json={"action": "approve-plan", "task_id": planning["id"]},
            )
            assert response.status_code == 200, response.text

            proved = by_state["proved"]
            response = client.post(
                f"{BASE}/actions",
                headers=headers,
                json={"action": "release", "task_id": proved["id"]},
            )
            assert response.status_code == 200, response.text

            response = client.post(
                f"{BASE}/readiness",
                headers=headers,
                json={"repo": str(home / "repo")},
            )
            assert response.status_code == 202, response.text
            job = wait_job(client, response.json()["job"]["id"])
            assert job["status"] == "succeeded", job
            print("actions smoke: ok")
            print("home:", home)
    finally:
        if temporary and not args.keep:
            shutil.rmtree(home.parent, ignore_errors=True)


if __name__ == "__main__":
    main()
