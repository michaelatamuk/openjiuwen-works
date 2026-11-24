"""Smoke a built wheel from an isolated extraction directory.

    python scripts/smoke_wheel.py --wheel dist/openjiuwen_works-0.0.1-py3-none-any.whl

The wheel is unpacked into a temp site directory and put first on PYTHONPATH, so every command
imports the packaged code, flows and workers instead of the source tree.
"""

# ruff: noqa: S101 - this smoke script asserts its gate steps

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BASE = "/api/v1"
FACTORY = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run(
    python: Path, site: Path, home: Path, *args: str, timeout: float = 120.0
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(site), env.get("PYTHONPATH", "")]).strip(os.pathsep)
    return subprocess.run(
        [str(python), "-m", "works", "--home", str(home), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


def payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    if not lines:
        raise AssertionError(f"no JSON output; stderr={result.stderr}")
    return json.loads(lines[-1])


def health(port: int, timeout: float = 1.0) -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}{BASE}/health", timeout=timeout
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        return
    with contextlib.suppress(OSError):
        os.kill(pid, 9)


def find_identity(site: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(site), env.get("PYTHONPATH", "")]).strip(os.pathsep)
    completed = subprocess.run(
        [sys.executable, "-c", "import works; print(works.__file__)"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    loaded = Path(completed.stdout.strip()).resolve()
    assert site.resolve() in loaded.parents, f"imported {loaded}, not the wheel"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument(
        "--full",
        action="store_true",
        help=(
            "also seed a home, stream an ask and run team verify (needs agent-core and a model key)"
        ),
    )
    args = parser.parse_args()
    wheel = args.wheel.expanduser().resolve()
    assert wheel.is_file(), f"wheel not found: {wheel}"

    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("WORKS_MODEL_KEY")
    agent_python = Path(
        os.environ.get("WORKS_AGENT_PYTHON")
        or r"C:\Workspace\openjiuwen\agent-core\.venv\Scripts\python.exe"
    )
    full = bool(args.full and key and agent_python.exists())
    if args.full and not full:
        print("[skip] --full needs a model key and the agent-core Python")

    python = Path(sys.executable)
    temporary = Path(tempfile.mkdtemp(prefix="works-wheel-"))
    site = temporary / "site"
    home = temporary / "home"
    site.mkdir(parents=True)
    home.mkdir(parents=True)
    try:
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(site)
        find_identity(site)
        print(f"[ok] imports the wheel from {site}")

        for command in (("--help",), ("version",)):
            result = run(python, site, home, *command)
            assert result.returncode == 0, result.stdout + result.stderr
        print("[ok] help and version")

        doctor = run(python, site, home, "doctor", "--json")
        checks = payload(doctor).get("checks", [])
        flow = next((item for item in checks if item.get("name") == "flow"), None)
        assert flow is not None and flow.get("status") == "ok", checks
        assert (home / "flows" / "fix-issue.yaml").is_file()
        assert (home / "flows" / "fix-issue" / "prompts" / "build.md").is_file()
        print("[ok] doctor loads the packaged flow into the fresh home")

        task_id = ""
        if full:
            seed = subprocess.run(
                [
                    str(python),
                    str(FACTORY / "scripts" / "seed_home.py"),
                    "--root",
                    str(home),
                    "--force",
                ],
                capture_output=True,
                text=True,
                timeout=600,
            )
            assert seed.returncode == 0, seed.stdout + seed.stderr
            status = payload(run(python, site, home, "status", "--json"))
            tasks = status.get("tasks") or []
            proved = next(
                (item for item in tasks if item.get("state") == "proved"),
                None,
            )
            assert proved is not None, status
            task_id = str(proved["id"])
            print(f"[ok] seeded a proved task through the wheel: {task_id}")

        port = free_port()
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(site), env.get("PYTHONPATH", "")]).strip(
            os.pathsep
        )
        log = (temporary / "ui.log").open("ab")
        ui = subprocess.Popen(
            [
                str(python),
                "-m",
                "works",
                "--home",
                str(home),
                "ui",
                "--port",
                str(port),
                "--write" if full else "--read-only",
                "--no-open",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
        )
        try:
            deadline = time.monotonic() + 60
            body = None
            while time.monotonic() < deadline:
                body = health(port)
                if body is not None:
                    break
                time.sleep(0.1)
            assert body is not None and Path(str(body.get("root"))).resolve() == home.resolve()
            print(f"[ok] works ui served the wheel on {port}")

            if full:
                token = (
                    (home / ".works" / "state" / "http-token").read_text(encoding="utf-8").strip()
                )
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}{BASE}/ask/stream",
                    data=json.dumps(
                        {"task_id": task_id, "question": "What is the verdict?"}
                    ).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=240) as response:  # noqa: S310
                    text = response.read().decode("utf-8")
                events = [
                    json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")
                ]
                assert any(item.get("type") == "done" for item in events), text
                print("[ok] ask streamed a model answer through the packaged worker")

                team = run(python, site, home, "team", "verify", task_id, "--json", timeout=240)
                assert team.returncode == 0, team.stdout + team.stderr
                result = payload(team)
                assert result.get("verdict") == "allow", result
                print("[ok] team verify ran the packaged worker")
        finally:
            kill_tree(ui.pid)
            ui.wait(timeout=10)
            log.close()

        print("wheel smoke: ok")
        return 0
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
