"""Command execution with timeouts, a sanitised environment and typed results."""

from __future__ import annotations

import contextlib
import hashlib
import os

# The runner is the one place that starts processes; argv is always a list.
import subprocess  # nosec B404
import sys
import threading
import time
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from works.adapters.processes import job
from works.domain.records import CommandRecord

# A job sets this for its worker thread; SubprocessRunner kills the child tree when it flips.
CURRENT_CANCEL: ContextVar[threading.Event | None] = ContextVar("works_job_cancel", default=None)

_SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL")


def sanitize_env(environ: dict[str, str], *, allow: tuple[str, ...] = ()) -> dict[str, str]:
    """Drop anything that looks like a credential before a command sees it.

    There is no blanket `WORKS_` exception: a verifier must not inherit the builder's model key.
    A caller that really needs a variable passes it in `allow` or in the explicit command env.
    """
    clean: dict[str, str] = {}
    for name, value in environ.items():
        if name in allow:
            clean[name] = value
            continue
        if any(marker in name.upper() for marker in _SECRET_MARKERS):
            continue
        clean[name] = value
    return clean


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    cwd: str
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str
    timed_out: bool = False
    env_extra: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def output(self) -> str:
        return self.stdout + ("\n" if self.stdout and self.stderr else "") + self.stderr

    @property
    def output_sha256(self) -> str:
        return hashlib.sha256(self.output.encode("utf-8", errors="replace")).hexdigest()

    def record(self, step: str) -> CommandRecord:
        return CommandRecord(
            step=step,
            argv=list(self.argv),
            cwd=self.cwd,
            exit_code=self.exit_code,
            duration_ms=self.duration_ms,
            timed_out=self.timed_out,
            output_sha256=self.output_sha256,
            stdout_tail=self.stdout[-2000:],
            stderr_tail=self.stderr[-2000:],
        )


class CommandRunner(Protocol):
    def run(
        self,
        argv: list[str],
        cwd: Path,
        *,
        env: dict[str, str] | None = None,
        timeout_s: int = 600,
    ) -> CommandResult: ...


def _kill_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],  # nosec B603 B607
            capture_output=True,
            check=False,
        )
    else:
        import signal

        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError, OSError):
        process.kill()


def _is_linux() -> bool:
    # A helper keeps mypy from narrowing sys.platform to the host value and calling the Linux
    # branch unreachable on macOS.
    return sys.platform.startswith("linux")


def _pdeathsig_hook() -> Callable[[], None] | None:
    """Linux: kill the command when the daemon dies, even by `SIGKILL`.

    `PR_SET_PDEATHSIG` is delivered to the direct child, which is the command Works started.
    macOS has no equivalent, so that platform keeps the documented gap.
    """
    if not _is_linux():
        return None
    import ctypes
    import signal

    libc = ctypes.CDLL(None, use_errno=True)
    parent = os.getpid()

    def hook() -> None:
        # Runs in the forked child before exec; keep it to one syscall.
        libc.prctl(1, signal.SIGKILL, 0, 0, 0)  # PR_SET_PDEATHSIG
        if os.getppid() != parent:  # the daemon died before prctl took effect
            os.kill(os.getpid(), signal.SIGKILL)

    return hook


class SubprocessRunner:
    def __init__(self, *, extra_env: dict[str, str] | None = None) -> None:
        self._extra_env = dict(extra_env or {})

    def _environment(self, env: dict[str, str] | None) -> dict[str, str]:
        merged = sanitize_env(dict(os.environ), allow=("PYTHONPATH",))
        merged.update(self._extra_env)
        merged.update(env or {})
        merged.setdefault("PYTHONUNBUFFERED", "1")
        merged.setdefault("PYTHONIOENCODING", "utf-8")
        # A same-size patch within the same second can leave a stale .pyc in the worktree.
        merged.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        merged.setdefault("NO_COLOR", "1")
        merged.setdefault("CI", "1")
        return merged

    def run(
        self,
        argv: list[str],
        cwd: Path,
        *,
        env: dict[str, str] | None = None,
        timeout_s: int = 600,
    ) -> CommandResult:
        started = time.monotonic()
        kwargs: dict[str, Any] = {}  # platform-specific: a new process group per command
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
            hook = _pdeathsig_hook()
            if hook is not None:
                # The child dies with the daemon even if the daemon is SIGKILLed.
                kwargs["preexec_fn"] = hook
        process = subprocess.Popen(  # nosec B603
            argv,
            cwd=str(cwd),
            env=self._environment(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **kwargs,
        )
        job_handle = job.attach(process)
        cancel = CURRENT_CANCEL.get()
        stop = threading.Event()
        watcher: threading.Thread | None = None
        if cancel is not None:

            def watch() -> None:
                while not stop.wait(0.05):
                    if cancel.is_set():
                        _kill_tree(process)
                        return

            watcher = threading.Thread(target=watch, name="works-command-cancel", daemon=True)
            watcher.start()
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(process)
            stdout, stderr = process.communicate()
        finally:
            stop.set()
            if watcher is not None:
                watcher.join(timeout=1)
            job.release(job_handle)
        duration_ms = int((time.monotonic() - started) * 1000)
        return CommandResult(
            argv=tuple(argv),
            cwd=str(cwd),
            exit_code=process.returncode if process.returncode is not None else -1,
            duration_ms=duration_ms,
            stdout=stdout or "",
            stderr=stderr or "",
            timed_out=timed_out,
            env_extra=dict(env or {}),
        )
