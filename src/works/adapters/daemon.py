"""Daemon bookkeeping and process control for one Works home.

The daemon is a normal local process; this module owns the small amount of state needed to find
it again: an identity file, a per-home lock, health checks and a graceful stop. Everything here is
standard library only so the CLI can use it without the `server` extra.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import os
import signal
import subprocess  # nosec B404 - spawns our own module, never a shell
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import IO, Any

from works.adapters.queue.atomic import atomic_write
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError, NotFoundError

INFO_FILE = "daemon.json"
LOCK_FILE = "daemon.lock"
TOKEN_FILE = "http-token"  # noqa: S105  # nosec B105 - a file name, not a secret
LOG_FILE = "daemon.log"
HEALTH_TIMEOUT = 1.5
START_TIMEOUT = 25.0
STOP_TIMEOUT = 15.0
START_TOLERANCE = 120.0
ALLOW_ENV = frozenset(
    {
        "PATH",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "COMMONPROGRAMFILES",
        "COMSPEC",
        "PATHEXT",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "LANG",
        "LC_ALL",
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "PYTHONUTF8",
        "PYTHONIOENCODING",
        "USERNAME",
        "USERDOMAIN",
    }
)


@dataclass(frozen=True)
class DaemonInfo:
    pid: int
    host: str
    port: int
    home: str
    started_at: float
    token_path: str

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def probe_base_url(self) -> str:
        """The address a client on this machine can actually call for a wildcard bind."""
        return f"http://{_probe_host(self.host)}:{self.port}"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def info_path(paths: WorksPaths) -> Path:
    return paths.state / INFO_FILE


def lock_path(paths: WorksPaths) -> Path:
    return paths.state / LOCK_FILE


def log_path(paths: WorksPaths) -> Path:
    return paths.state / LOG_FILE


def token_path(paths: WorksPaths) -> Path:
    return paths.state / TOKEN_FILE


def read_token(info: DaemonInfo) -> str:
    try:
        return Path(info.token_path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _probe_host(host: str) -> str:
    """A wildcard bind is reachable on loopback; its literal address is not trusted."""
    if host in ("0.0.0.0", ""):  # noqa: S104  # nosec B104 - detecting, not binding
        return "127.0.0.1"
    if host == "::":
        return "::1"
    return host


def fetch_health(host: str, port: int, *, timeout: float = HEALTH_TIMEOUT) -> dict[str, Any] | None:
    url = f"http://{_probe_host(host)}:{port}/api/v1/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _health_root_matches(info: DaemonInfo, payload: dict[str, Any] | None) -> bool:
    if payload is None or not payload.get("ok"):
        return False
    root = str(payload.get("root") or "")
    if not root:
        return False
    with contextlib.suppress(OSError):
        return Path(root).resolve() == Path(info.home).resolve()
    return False


def _health_matches(info: DaemonInfo) -> bool:
    return _health_root_matches(info, fetch_health(info.host, info.port))


def _windows_alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    windll = getattr(ctypes, "WinDLL", None)
    if windll is None:
        return False
    kernel32 = windll("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return bool(code.value == still_active)
    finally:
        kernel32.CloseHandle(handle)


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_started_at(pid: int) -> float | None:
    """Best-effort process creation time, used to detect a reused pid."""
    if pid <= 0:
        return None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        windll = getattr(ctypes, "WinDLL", None)
        if windll is None:
            return None
        kernel32 = windll("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return None
        try:
            created = wintypes.FILETIME()
            exited = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(exited),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                return None
            ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
            # FILETIME counts 100 ns intervals since 1601-01-01.
            return ticks / 10_000_000 - 11_644_473_600
        finally:
            kernel32.CloseHandle(handle)
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        start_ticks = int(fields[21])
        btime = 0
        for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines():
            if line.startswith("btime "):
                btime = int(line.split()[1])
                break
        sysconf = getattr(os, "sysconf", None)
        ticks_per_second = float(sysconf("SC_CLK_TCK")) if sysconf else 100.0
        return float(btime + start_ticks / ticks_per_second)
    except (OSError, ValueError, IndexError):
        return None


def _pid_is_the_daemon(info: DaemonInfo) -> bool:
    if not pid_alive(info.pid):
        return False
    started = process_started_at(info.pid)
    if started is None:
        return True
    return abs(started - info.started_at) <= START_TOLERANCE


def clear_info(paths: WorksPaths) -> None:
    with contextlib.suppress(FileNotFoundError):
        info_path(paths).unlink()


def load_info(paths: WorksPaths) -> DaemonInfo | None:
    """Read the identity file without probing the process; None when absent or malformed."""
    try:
        payload = json.loads(info_path(paths).read_text(encoding="utf-8"))
        return DaemonInfo(
            pid=int(payload["pid"]),
            host=str(payload["host"]),
            port=int(payload["port"]),
            home=str(payload["home"]),
            started_at=float(payload["started_at"]),
            token_path=str(payload["token_path"]),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def current_daemon(paths: WorksPaths) -> DaemonInfo | None:
    """Return the live daemon for this home, clearing a stale identity file."""
    path = info_path(paths)
    info = load_info(paths)
    if info is None:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        return None
    if Path(info.home).resolve() != paths.root.resolve():
        clear_info(paths)
        return None
    if not _pid_is_the_daemon(info):
        clear_info(paths)
        return None
    health = fetch_health(info.host, info.port)
    if health is None:
        # The process is alive but not answering yet: starting up or shutting down.
        return None
    if not _health_root_matches(info, health):
        clear_info(paths)
        return None
    return info


def write_info(paths: WorksPaths, info: DaemonInfo) -> None:
    atomic_write(
        info_path(paths),
        json.dumps(info.as_dict(), ensure_ascii=False, indent=2) + "\n",
    )


class HomeLock:
    """An exclusive, process-lifetime lock for one home, so two writable daemons never race."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: IO[bytes] | None = None

    def acquire(self) -> bool:
        if self._file is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            module = importlib.import_module("msvcrt" if os.name == "nt" else "fcntl")
            if os.name == "nt":
                module.locking(handle.fileno(), module.LK_NBLCK, 1)
            else:
                module.flock(handle.fileno(), module.LOCK_EX | module.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self._file = handle
        return True

    def release(self) -> None:
        if self._file is None:
            return
        with contextlib.suppress(OSError):
            self._file.seek(0)
            module = importlib.import_module("msvcrt" if os.name == "nt" else "fcntl")
            if os.name == "nt":
                module.locking(self._file.fileno(), module.LK_UNLCK, 1)
            else:
                module.flock(self._file.fileno(), module.LOCK_UN)
        self._file.close()
        self._file = None


def acquire_lock(paths: WorksPaths) -> HomeLock | None:
    lock = HomeLock(lock_path(paths))
    return lock if lock.acquire() else None


def snapshot_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key in ALLOW_ENV or key.startswith("WORKS_")
    }


def current_info(paths: WorksPaths, *, host: str, port: int) -> DaemonInfo:
    pid = os.getpid()
    return DaemonInfo(
        pid=pid,
        host=host,
        port=port,
        home=str(paths.root),
        started_at=process_started_at(pid) or time.time(),
        token_path=str(token_path(paths)),
    )


def _daemon_command(
    paths: WorksPaths,
    *,
    host: str,
    port: int,
    write: bool,
    trusted_hosts: tuple[str, ...] = (),
    allow_remote: bool = False,
    open_lan: bool = False,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "works",
        "--home",
        str(paths.root),
        "daemon",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if write:
        command.append("--write")
    if allow_remote:
        command.append("--allow-remote")
    if open_lan:
        command.append("--open-lan")
    for trusted in trusted_hosts:
        command.extend(["--trusted-host", trusted])
    return command


def _tail(path: Path, limit: int = 2000) -> str:
    with contextlib.suppress(OSError):
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[-limit:]
    return ""


def start_daemon(
    paths: WorksPaths,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    write: bool = False,
    timeout: float = START_TIMEOUT,
    trusted_hosts: tuple[str, ...] = (),
    allow_remote: bool = False,
    open_lan: bool = False,
) -> DaemonInfo:
    existing = current_daemon(paths)
    if existing is not None:
        return existing
    log = log_path(paths)
    log.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log.open("ab")
    kwargs: dict[str, Any] = {
        "cwd": str(paths.root),
        "env": snapshot_env(),
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": log_handle,
        "close_fds": True,
    }
    if os.name == "nt":
        flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
        flags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    try:
        process = subprocess.Popen(  # noqa: S603  # nosec B603 - fixed argv, no shell
            _daemon_command(
                paths,
                host=host,
                port=port,
                write=write,
                trusted_hosts=trusted_hosts,
                allow_remote=allow_remote,
                open_lan=open_lan,
            ),
            **kwargs,
        )
    finally:
        log_handle.close()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = load_info(paths)
        if found is not None and _pid_is_the_daemon(found) and _health_matches(found):
            return found
        code = process.poll()
        # The venv python on Windows may be a launcher: it can exit 0 while the real
        # interpreter keeps serving, so only a non-zero launcher exit is fatal.
        if code is not None and code != 0:
            clear_info(paths)
            raise ConfigError(f"the daemon exited with code {code}; log: {log}\n{_tail(log)}")
        time.sleep(0.2)
    with contextlib.suppress(OSError):
        process.terminate()
    raise ConfigError(f"the daemon did not become healthy in {timeout:.0f}s; log: {log}")


def _post_shutdown(info: DaemonInfo, token: str, *, timeout: float = 3.0) -> bool:
    request = urllib.request.Request(  # noqa: S310 - loopback
        f"{info.probe_base_url}/api/v1/admin/shutdown",
        data=b"{}",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout):  # noqa: S310  # nosec B310
            return True
    except urllib.error.HTTPError as exc:
        return exc.code < 400
    except OSError:
        return False


def _signal_stop(pid: int) -> None:
    if os.name == "nt":
        ctrl_break = getattr(signal, "CTRL_BREAK_EVENT", None)
        if ctrl_break is not None:
            with contextlib.suppress(OSError, ValueError):
                os.kill(pid, ctrl_break)
                return
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)
        return
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGTERM)


def _force_stop(pid: int) -> None:
    if os.name == "nt":
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)
        return
    with contextlib.suppress(OSError):
        os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))


def _still_serving(info: DaemonInfo) -> bool:
    """A health response from our home proves the pid still belongs to this daemon."""
    if not pid_alive(info.pid):
        return False
    return _health_matches(info)


def _wait_gone(info: DaemonInfo, timeout: float) -> bool:
    """Wait for the process itself, not just its socket: a hung server keeps the home lock."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_is_the_daemon(info):
            return True
        time.sleep(0.1)
    return not _pid_is_the_daemon(info)


def stop_daemon(paths: WorksPaths, *, timeout: float = STOP_TIMEOUT) -> DaemonInfo:
    info = current_daemon(paths)
    if info is None:
        raise NotFoundError(f"no daemon is running for {paths.root}")
    # An in-process server (tests, `works ui` in this interpreter) shares our pid: never kill it.
    self_hosted = info.pid == os.getpid()
    if not self_hosted and _still_serving(info) and not _post_shutdown(info, read_token(info)):
        _signal_stop(info.pid)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _still_serving(info):
            # The socket is closed, but Uvicorn can still be draining SSE clients and holding
            # `.works/state/daemon.lock`. Wait for the process, then force it.
            if not self_hosted and not _wait_gone(info, 5.0):
                _force_stop(info.pid)
                if not _wait_gone(info, 5.0):
                    raise ConfigError(f"the daemon (pid {info.pid}) is still holding the home")
            clear_info(paths)
            return info
        time.sleep(0.1)
    if self_hosted:
        raise ConfigError(f"the in-process daemon (pid {info.pid}) did not stop")
    _force_stop(info.pid)
    if not _wait_gone(info, 5.0):
        raise ConfigError(f"the daemon (pid {info.pid}) did not stop")
    clear_info(paths)
    return info
