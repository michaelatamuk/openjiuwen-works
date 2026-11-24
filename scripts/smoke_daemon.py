"""Phase 6 gate: detached daemon, UI, dispatch, crash recovery.

    python scripts/smoke_daemon.py
    python scripts/smoke_daemon.py --home %TEMP%\\opencode\\works-daemon-smoke --keep

The script seeds a home, starts a read-only UI app on a second port, starts a detached writable
daemon, runs queued tasks through `POST /dispatch` while stopping the UI, runs another task through
`works run --daemon`, then kills the daemon mid-run and checks restart reconciliation before a
graceful stop.
"""

# ruff: noqa: S101 - this smoke script asserts its gate steps

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

FACTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY))

from scripts.seed_home import DEFAULT_NOW, seed  # noqa: E402

from works.adapters import daemon as daemons  # noqa: E402
from works.adapters.queue.store import Queue  # noqa: E402
from works.config.paths import WorksPaths  # noqa: E402

FINAL = frozenset({"succeeded", "failed", "cancelled"})
BASE = "/api/v1"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def cli(home: Path, *args: str, timeout: float = 180.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "works", "--home", str(home), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def payload(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    if not lines:
        raise AssertionError(f"no JSON output; stderr={result.stderr}")
    return json.loads(lines[-1])


def request(
    base: str,
    method: str,
    path: str,
    *,
    token: str = "",
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(  # noqa: S310  # nosec B310 - loopback
        f"{base}{path}", data=data, method=method, headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310  # nosec B310
            return int(response.status), json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return int(exc.code), json.loads(exc.read() or b"{}")


def wait_health(base: str, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code, body = request(base, "GET", f"{BASE}/health", timeout=1.0)
        if code == 200 and body.get("ok"):
            return body
        time.sleep(0.1)
    raise AssertionError(f"{base} never became healthy")


def wait_job(
    base: str, token: str, job_id: str, *, until: str = "final", timeout: float = 120.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code, body = request(base, "GET", f"{BASE}/jobs/{job_id}", token=token)
        assert code == 200, body
        status = str(body.get("status"))
        if status == until or (until == "final" and status in FINAL):
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach {until}")


def wait_running_or_final(
    base: str, token: str, job_id: str, *, timeout: float = 120.0
) -> tuple[dict[str, Any], bool]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code, body = request(base, "GET", f"{BASE}/jobs/{job_id}", token=token)
        assert code == 200, body
        status = str(body.get("status"))
        if status == "running":
            return body, True
        if status in FINAL:
            return body, False
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not start")


def create_task(base: str, token: str, home: Path, ref: str) -> str:
    code, body = request(
        base,
        "POST",
        f"{BASE}/tasks",
        token=token,
        body={
            "repo": str(home / "repo"),
            "product": "Fixture",
            "ref": ref,
            "title": f"Daemon smoke {ref}",
            "flow": "fix-issue",
        },
    )
    assert code in (200, 201), body
    return str(body["task"]["id"])


def run_options(home: Path) -> dict[str, Any]:
    return {
        "approve_plan": True,
        "scenarios": str(home / "scenarios" / "fix-add.yaml"),
        "trace": str(FACTORY / "fixtures" / "traces" / "fix-add.json"),
    }


def wait_dead(pid: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not daemons.pid_alive(pid):
            return
        time.sleep(0.05)
    raise AssertionError(f"pid {pid} did not exit")


def kill_tree(pid: int) -> None:
    """Kill a launcher and the real interpreter it spawned (Windows venv python)."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=20,
        )
        return
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGKILL)


def wait_unhealthy(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if daemons.fetch_health("127.0.0.1", port, timeout=0.5) is None:
            return
        time.sleep(0.1)
    raise AssertionError(f"port {port} is still serving")


def tail(path: Path, limit: int = 4000) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-limit:]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=None)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    temporary = args.home is None
    home = (args.home or Path(tempfile.mkdtemp(prefix="works-daemon-smoke-")) / "home").resolve()
    if home.exists():
        shutil.rmtree(home)
    seed(home, now=DEFAULT_NOW)

    port = free_port()
    ui_port = free_port()
    while ui_port == port:
        ui_port = free_port()
    base = f"http://127.0.0.1:{port}"
    ui_base = f"http://127.0.0.1:{ui_port}"
    ui_state = None
    ui_thread = None
    daemon_pid = 0
    token = ""
    try:
        from works.interfaces.api.app import create_app
        from works.interfaces.api.wiring import build_state as build_app_state
        from works.interfaces.cli.commands.daemon import run_server

        ui_state = build_app_state(home, writable=False)
        ui_thread = threading.Thread(
            target=run_server,
            kwargs={
                "app": create_app(state=ui_state),
                "state": ui_state,
                "host": "127.0.0.1",
                "port": ui_port,
                "write": False,
                "log_level": "critical",
            },
            name="works-smoke-ui",
            daemon=True,
        )
        ui_thread.start()
        wait_health(ui_base, timeout=40.0)
        print(f"[ok] read-only UI on {ui_port}")

        started = cli(home, "daemon", "start", "--write", "--port", str(port), "--json")
        assert started.returncode == 0, started.stderr
        info = payload(started)
        daemon_pid = int(info["pid"])
        wait_health(base)
        token = daemons.token_path(WorksPaths(home)).read_text(encoding="utf-8").strip()
        print(f"[ok] detached daemon {daemon_pid} on {port}")

        create_task(base, token, home, "DAEMON-SMOKE-A")
        create_task(base, token, home, "DAEMON-SMOKE-B")
        code, body = request(
            base,
            "POST",
            f"{BASE}/dispatch",
            token=token,
            body={"limit": 5, **run_options(home)},
        )
        assert code == 202, body
        job_id = str(body["job"]["id"])
        _, was_running = wait_running_or_final(base, token, job_id)
        assert ui_state is not None and ui_thread is not None
        ui_state.stop_event.set()
        ui_thread.join(10)
        assert not ui_thread.is_alive(), "the UI thread did not stop"
        wait_unhealthy(ui_port)
        assert was_running, "dispatch finished before the UI kill"
        print("[ok] killed the UI while dispatch was running")
        job = wait_job(base, token, job_id)
        assert job["status"] == "succeeded", job
        assert job["result"]["selected"] >= 3, job
        for item in job["result"]["runs"]:
            assert "run" in item, item
            assert item["run"]["state"] == "proved", item
        print("[ok] dispatch survived the UI and every run proved")

        task_b = create_task(base, token, home, "DAEMON-SMOKE-2")
        cli_run = cli(
            home,
            "run",
            task_b,
            "--daemon",
            "--approve-plan",
            "--scenarios",
            str(home / "scenarios" / "fix-add.yaml"),
            "--trace",
            str(FACTORY / "fixtures" / "traces" / "fix-add.json"),
            "--json",
        )
        assert cli_run.returncode == 0, cli_run.stdout + cli_run.stderr
        cli_body = payload(cli_run)
        assert cli_body["ok"] is True, cli_body
        assert cli_body["run"]["task_id"] == task_b, cli_body
        assert cli_body["run"]["state"] == "proved", cli_body
        print("[ok] works run --daemon returned the standalone JSON shape")

        standalone = cli(
            home,
            "run",
            task_b,
            "--approve-plan",
            "--scenarios",
            str(home / "scenarios" / "fix-add.yaml"),
            "--trace",
            str(FACTORY / "fixtures" / "traces" / "fix-add.json"),
            "--json",
        )
        assert standalone.returncode == 6, standalone.stdout + standalone.stderr
        assert payload(standalone)["error"]["code"] == "config_error"
        print("[ok] standalone run refuses while the daemon owns the home")

        conflict = cli(home, "ui", "--write", "--no-open", "--port", str(free_port()), "--json")
        assert conflict.returncode == 6, conflict.stdout + conflict.stderr
        assert payload(conflict)["error"]["code"] == "config_error"
        print("[ok] a second writable UI is refused")

        task_c = ""
        crash_job = ""
        for attempt in range(1, 6):
            task_c = create_task(base, token, home, f"DAEMON-SMOKE-C{attempt}")
            code, body = request(
                base,
                "POST",
                f"{BASE}/runs",
                token=token,
                body={"task_id": task_c, **run_options(home)},
            )
            assert code == 202, body
            crash_job = str(body["job"]["id"])
            started_job, running = wait_running_or_final(base, token, crash_job)
            if running:
                break
            assert started_job["status"] == "succeeded", started_job
        else:
            raise AssertionError("could not catch a run in flight")
        kill_tree(daemon_pid)
        wait_dead(daemon_pid)
        wait_unhealthy(port)
        print("[ok] killed the daemon mid-run")

        restarted = cli(home, "daemon", "start", "--write", "--port", str(port), "--json")
        assert restarted.returncode == 0, restarted.stderr
        daemon_pid = int(payload(restarted)["pid"])
        wait_health(base)
        failed = wait_job(base, token, crash_job)
        assert failed["status"] == "failed", failed
        assert "daemon restarted" in str(failed.get("error")), failed
        owner = Queue(WorksPaths(home)).owner(task_c)
        assert owner is None, f"stale owner remains: {owner}"
        print("[ok] restart failed the orphan job and released the task owner")

        recovered = create_task(base, token, home, "DAEMON-SMOKE-RECOVERED")
        retry = cli(
            home,
            "run",
            recovered,
            "--daemon",
            "--approve-plan",
            "--scenarios",
            str(home / "scenarios" / "fix-add.yaml"),
            "--trace",
            str(FACTORY / "fixtures" / "traces" / "fix-add.json"),
            "--json",
        )
        assert retry.returncode == 0, retry.stdout + retry.stderr
        assert payload(retry)["run"]["task_id"] == recovered, retry.stdout
        assert payload(retry)["run"]["state"] == "proved", retry.stdout
        print("[ok] the restarted daemon runs a new task")

        stopped = cli(home, "daemon", "stop", "--json")
        assert stopped.returncode == 0, stopped.stderr
        assert payload(stopped)["stopped"] is True
        assert daemons.current_daemon(WorksPaths(home)) is None
        print("[ok] graceful stop")
        print("daemon gate: ok")
    except Exception:
        print("\n--- daemon log ---")
        print(tail(home / ".works" / "state" / "daemon.log"))
        if daemon_pid and daemons.pid_alive(daemon_pid):
            kill_tree(daemon_pid)
        raise
    finally:
        if ui_state is not None:
            ui_state.stop_event.set()
        if ui_thread is not None and ui_thread.is_alive():
            ui_thread.join(5)
        if daemon_pid and daemons.pid_alive(daemon_pid):
            with contextlib.suppress(Exception):
                cli(home, "daemon", "stop", "--json", timeout=20)
        if temporary and not args.keep:
            shutil.rmtree(home.parent, ignore_errors=True)


if __name__ == "__main__":
    main()
