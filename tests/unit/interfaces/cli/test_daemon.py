from __future__ import annotations

import contextlib
import io
import json
import os
import socket
import threading
import time
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass

from works.adapters import daemon
from works.adapters.queue.store import Queue
from works.domain.records import Source, SourceKind
from works.interfaces.api.app import create_app
from works.interfaces.api.wiring import build_state
from works.interfaces.cli.commands.daemon import run_server
from works.interfaces.cli.main import main


@dataclass(frozen=True)
class Result:
    exit_code: int
    stdout: str
    stderr: str


def invoke(paths, *args: str) -> Result:
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--home", str(paths.root), *args])
    except SystemExit as exc:
        code = int(exc.code) if exc.code is not None else 0
    return Result(code, out.getvalue(), err.getvalue())


def payload(result: Result) -> dict:
    return json.loads(result.stdout.strip().splitlines()[-1])


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_daemon(paths, timeout: float = 15.0) -> daemon.DaemonInfo:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = daemon.current_daemon(paths)
        if info is not None:
            return info
        time.sleep(0.05)
    raise AssertionError("the in-process daemon never became healthy")


class LiveDaemon:
    def __init__(self, paths) -> None:
        self.paths = paths
        self.port = free_port()
        self.state = build_state(paths, writable=True)
        self.app = create_app(state=self.state)
        self.thread = threading.Thread(
            target=run_server,
            kwargs={
                "app": self.app,
                "state": self.state,
                "host": "127.0.0.1",
                "port": self.port,
                "write": True,
                "log_level": "critical",
            },
            name="works-test-daemon",
            daemon=True,
        )

    def __enter__(self) -> daemon.DaemonInfo:
        self.thread.start()
        return wait_for_daemon(self.paths)

    def __exit__(self, *exc) -> None:
        with contextlib.suppress(Exception):  # the test may already have stopped it
            daemon.stop_daemon(self.paths)
        self.thread.join(10)


def make_task(paths, repo, ref: str) -> str:
    task, _ = Queue(paths).submit(
        source=Source(kind=SourceKind.MANUAL, ref=ref, title=f"Run {ref}"),
        flow="fix-issue",
        product="Fixture",
        repo=str(repo.path),
    )
    return task.id


def test_status_and_stop_round_trip(paths) -> None:
    with LiveDaemon(paths) as info:
        assert info.pid == os.getpid()
        assert daemon.info_path(paths).is_file()

        status = invoke(paths, "daemon", "status", "--json")
        assert status.exit_code == 0, status.stderr
        body = payload(status)
        assert body["running"] is True
        assert body["pid"] == os.getpid()
        assert body["url"].startswith(f"http://127.0.0.1:{info.port}/")

        started = invoke(paths, "daemon", "start", "--json")
        assert started.exit_code == 0
        assert payload(started)["pid"] == os.getpid()

    assert daemon.current_daemon(paths) is None
    missing = invoke(paths, "daemon", "status", "--json")
    assert missing.exit_code == 5
    assert payload(missing)["running"] is False


def test_the_cli_refuses_a_standalone_run_while_a_daemon_owns_the_home(paths) -> None:
    with LiveDaemon(paths):
        result = invoke(paths, "dispatch", "--json")
    assert result.exit_code == 6
    assert payload(result)["error"]["code"] == "config_error"


def test_run_through_the_daemon_prints_the_same_json(paths, repo, factory_root) -> None:
    task_id = make_task(paths, repo, "DAEMON-1")
    scenarios = str(factory_root / "fixtures" / "scenarios" / "fix-add.yaml")
    trace = str(factory_root / "fixtures" / "traces" / "fix-add.json")
    with LiveDaemon(paths):
        result = invoke(
            paths,
            "run",
            task_id,
            "--approve-plan",
            "--scenarios",
            scenarios,
            "--trace",
            trace,
            "--daemon",
            "--json",
        )
    assert result.exit_code == 0, result.stdout + result.stderr
    body = payload(result)
    assert body["ok"] is True
    assert body["run"]["task_id"] == task_id
    assert body["run"]["state"] == "proved"


def test_dispatch_through_the_daemon_selects_the_queue(paths, repo, factory_root) -> None:
    first = make_task(paths, repo, "DAEMON-2")
    second = make_task(paths, repo, "DAEMON-3")
    scenarios = str(factory_root / "fixtures" / "scenarios" / "fix-add.yaml")
    trace = str(factory_root / "fixtures" / "traces" / "fix-add.json")
    with LiveDaemon(paths):
        result = invoke(
            paths,
            "dispatch",
            "--limit",
            "5",
            "--approve-plan",
            "--scenarios",
            scenarios,
            "--trace",
            trace,
            "--daemon",
            "--json",
        )
    assert result.exit_code == 0, result.stdout + result.stderr
    body = payload(result)
    assert body["selected"] == 2
    assert {item["task_id"] for item in body["runs"]} == {first, second}
