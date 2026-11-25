from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from works.adapters import daemon


def make_info(paths, **overrides) -> daemon.DaemonInfo:
    values = {
        "pid": os.getpid(),
        "host": "127.0.0.1",
        "port": 8765,
        "home": str(paths.root),
        "started_at": daemon.process_started_at(os.getpid()) or time.time(),
        "token_path": str(daemon.token_path(paths)),
    }
    values.update(overrides)
    return daemon.DaemonInfo(**values)


def test_info_round_trip_and_health_identity(paths, monkeypatch) -> None:
    info = make_info(paths)
    daemon.write_info(paths, info)
    monkeypatch.setattr(
        daemon,
        "fetch_health",
        lambda host, port, timeout=1.5: {"ok": True, "root": str(paths.root)},
    )
    assert daemon.current_daemon(paths) == info


def test_a_daemon_for_another_home_is_not_this_home(paths, monkeypatch) -> None:
    info = make_info(paths)
    daemon.write_info(paths, info)
    monkeypatch.setattr(
        daemon,
        "fetch_health",
        lambda host, port, timeout=1.5: {"ok": True, "root": str(paths.root / "other")},
    )
    assert daemon.current_daemon(paths) is None
    assert not daemon.info_path(paths).exists()


def test_a_dead_pid_clears_the_identity_file(paths, monkeypatch) -> None:
    daemon.write_info(paths, make_info(paths, pid=999_999_999))
    monkeypatch.setattr(daemon, "pid_alive", lambda pid: False)
    assert daemon.current_daemon(paths) is None
    assert not daemon.info_path(paths).exists()


def test_a_malformed_identity_file_is_ignored(paths) -> None:
    daemon.info_path(paths).write_text("{not json", encoding="utf-8")
    assert daemon.current_daemon(paths) is None
    assert not daemon.info_path(paths).exists()


def test_token_is_read_from_the_identity_path(paths) -> None:
    token = daemon.token_path(paths)
    token.write_text("secret-token\n", encoding="utf-8")
    assert daemon.read_token(make_info(paths)) == "secret-token"


def test_lock_round_trip(paths) -> None:
    lock = daemon.acquire_lock(paths)
    assert lock is not None
    lock.release()
    again = daemon.acquire_lock(paths)
    assert again is not None
    again.release()


@pytest.mark.skipif(os.name != "nt", reason="Windows byte-range locks are per process")
def test_lock_is_exclusive_across_handles(paths) -> None:
    first = daemon.acquire_lock(paths)
    assert first is not None
    try:
        assert daemon.acquire_lock(paths) is None
    finally:
        first.release()


def test_snapshot_env_keeps_the_allow_list_and_works_values(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("WORKS_HOME", "works-home")
    monkeypatch.setenv("SECRET_TOKEN", "nope")
    env = daemon.snapshot_env()
    assert env["PATH"] == "/usr/bin"
    assert env["WORKS_HOME"] == "works-home"
    assert "SECRET_TOKEN" not in env


def test_snapshot_env_keeps_the_windows_identity(monkeypatch) -> None:
    monkeypatch.setenv("USERNAME", "someone")
    env = daemon.snapshot_env()
    assert env["USERNAME"] == "someone"


def test_info_file_shape(paths) -> None:
    info = make_info(paths, port=9000)
    daemon.write_info(paths, info)
    payload = json.loads(daemon.info_path(paths).read_text(encoding="utf-8"))
    assert payload == {
        "pid": info.pid,
        "host": "127.0.0.1",
        "port": 9000,
        "home": str(paths.root),
        "started_at": info.started_at,
        "token_path": str(daemon.token_path(paths)),
    }


def test_a_daemon_log_path_lives_in_state(paths) -> None:
    assert daemon.log_path(paths) == Path(paths.state) / "daemon.log"


def test_a_remote_launch_forwards_allow_remote(paths) -> None:
    command = daemon._daemon_command(
        paths,
        host="0.0.0.0",  # noqa: S104 - asserting the forwarded flag, not binding
        port=8771,
        write=True,
        trusted_hosts=("192.168.1.20",),
        allow_remote=True,
    )
    assert "--allow-remote" in command
    assert command[command.index("--trusted-host") + 1] == "192.168.1.20"


def test_a_loopback_launch_does_not_claim_remote(paths) -> None:
    command = daemon._daemon_command(paths, host="127.0.0.1", port=8765, write=False)
    assert "--allow-remote" not in command


def test_a_wildcard_bind_is_probed_on_loopback() -> None:
    assert daemon._probe_host("0.0.0.0") == "127.0.0.1"  # noqa: S104 - a literal, not a bind
    assert daemon._probe_host("::") == "::1"
    assert daemon._probe_host("192.168.1.20") == "192.168.1.20"


def test_open_lan_is_forwarded_to_the_child(paths) -> None:
    command = daemon._daemon_command(
        paths,
        host="192.168.1.20",
        port=8771,
        write=True,
        trusted_hosts=("192.168.1.20",),
        allow_remote=True,
        open_lan=True,
    )
    assert "--open-lan" in command


def _fake_clock(monkeypatch) -> dict[str, float]:
    clock = {"now": 0.0}
    monkeypatch.setattr(daemon.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        daemon.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + seconds)
    )
    return clock


def test_stop_waits_for_a_hung_process_to_release_the_home(paths, monkeypatch) -> None:
    info = make_info(paths, pid=999_999_999)
    daemon.write_info(paths, info)
    monkeypatch.setattr(daemon, "current_daemon", lambda _paths: info)
    monkeypatch.setattr(daemon, "_still_serving", lambda _info: False)
    _fake_clock(monkeypatch)
    checks = {"count": 0, "killed": 0}

    def is_daemon(_info) -> bool:
        checks["count"] += 1
        return checks["count"] < 10

    monkeypatch.setattr(daemon, "_pid_is_the_daemon", is_daemon)
    monkeypatch.setattr(
        daemon, "_force_stop", lambda pid: checks.__setitem__("killed", checks["killed"] + 1)
    )

    assert daemon.stop_daemon(paths) == info
    assert checks["killed"] == 0
    assert not daemon.info_path(paths).exists()


def test_stop_forces_a_process_that_never_exits(paths, monkeypatch) -> None:
    info = make_info(paths, pid=999_999_999)
    daemon.write_info(paths, info)
    monkeypatch.setattr(daemon, "current_daemon", lambda _paths: info)
    monkeypatch.setattr(daemon, "_still_serving", lambda _info: False)
    _fake_clock(monkeypatch)
    state = {"killed": False}

    monkeypatch.setattr(daemon, "_pid_is_the_daemon", lambda _info: not state["killed"])

    def force(pid: int) -> None:
        state["killed"] = True

    monkeypatch.setattr(daemon, "_force_stop", force)

    assert daemon.stop_daemon(paths) == info
    assert state["killed"] is True
    assert not daemon.info_path(paths).exists()


def test_stop_never_kills_the_process_that_hosts_the_server(paths, monkeypatch) -> None:
    info = make_info(paths)  # pid is this pytest process
    daemon.write_info(paths, info)
    monkeypatch.setattr(daemon, "current_daemon", lambda _paths: info)
    _fake_clock(monkeypatch)
    calls = {"serving": 0, "killed": 0}

    def serving(_info) -> bool:
        calls["serving"] += 1
        return calls["serving"] < 2

    monkeypatch.setattr(daemon, "_still_serving", serving)
    monkeypatch.setattr(
        daemon, "_force_stop", lambda pid: calls.__setitem__("killed", calls["killed"] + 1)
    )

    assert daemon.stop_daemon(paths) == info
    assert calls["killed"] == 0
    assert not daemon.info_path(paths).exists()
