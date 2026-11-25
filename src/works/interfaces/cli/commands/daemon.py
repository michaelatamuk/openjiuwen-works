"""The local daemon: foreground run, detached start, status and graceful stop."""

from __future__ import annotations

import argparse
import contextlib
import socket
import threading
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

from works.adapters import daemon as daemons
from works.domain.errors import EXIT_NOT_FOUND, ConfigError, NotFoundError
from works.interfaces.cli.commands.common import _emit, _paths

if TYPE_CHECKING:
    from fastapi import FastAPI

    from works.config.paths import WorksPaths
    from works.interfaces.api.wiring import AppState

LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


def _trusted_hosts(args: argparse.Namespace) -> tuple[str, ...]:
    extra = tuple(getattr(args, "trusted_host", None) or ())
    trusted = set(LOOPBACK)
    trusted.update(extra)
    if args.host not in LOOPBACK:
        if args.host in ("0.0.0.0", "::"):  # noqa: S104  # nosec B104 - validated remote bind
            if not extra:
                raise ConfigError(
                    "a wildcard bind needs --trusted-host for the address clients will use"
                )
        else:
            trusted.add(args.host)
    return tuple(sorted(trusted))


def _requires_read_auth(args: argparse.Namespace) -> bool:
    return args.host not in LOOPBACK


def _primary_ipv4() -> str:
    """The address this machine uses for the default route (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            candidate = str(probe.getsockname()[0])
            if candidate and not candidate.startswith("127."):
                return candidate
    except OSError:
        pass
    try:
        candidate = socket.gethostbyname(socket.gethostname())
    except OSError:
        return ""
    return candidate if not candidate.startswith("127.") else ""


def _display_host(info: daemons.DaemonInfo) -> str:
    """A wildcard bind prints as an address another machine can actually open."""
    if info.host not in ("0.0.0.0", "::"):  # noqa: S104  # nosec B104 - a comparison
        return info.host
    return _primary_ipv4() or "127.0.0.1"


def _bootstrap_url(info: daemons.DaemonInfo) -> str:
    url = f"http://{_display_host(info)}:{info.port}/"
    token = daemons.read_token(info)
    return f"{url}?bootstrap={quote(token)}" if token else url


def _payload(info: daemons.DaemonInfo, *, write: bool) -> dict[str, object]:
    payload: dict[str, object] = {"running": True, **info.as_dict()}
    payload["url"] = _bootstrap_url(info) if write else f"http://{_display_host(info)}:{info.port}/"
    payload["write"] = write
    return payload


def run_server(
    app: FastAPI,
    state: AppState,
    *,
    host: str,
    port: int,
    write: bool,
    log_level: str = "info",
) -> None:
    """Serve the app, own the home lock in write mode, and stop on the shutdown route."""
    import uvicorn

    lock = None
    paths = state.paths
    if write:
        lock = daemons.acquire_lock(paths)
        if lock is None:
            raise ConfigError(
                f"another writable daemon already owns {paths.root}; "
                "stop it with `works daemon stop`"
            )
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level=log_level,
            log_config=None,
            access_log=False,
        )
    )

    def watch() -> None:
        state.stop_event.wait()
        server.should_exit = True

    def announce() -> None:
        while not server.started and not state.stop_event.is_set():
            state.stop_event.wait(0.05)
        if server.started:
            daemons.write_info(paths, daemons.current_info(paths, host=host, port=port))

    watcher = threading.Thread(target=watch, name="works-daemon-stop", daemon=True)
    watcher.start()
    if write:
        threading.Thread(target=announce, name="works-daemon-announce", daemon=True).start()
    try:
        server.run()
    finally:
        if write:
            daemons.clear_info(paths)
        if lock is not None:
            lock.release()


def cmd_daemon(args: argparse.Namespace) -> int:
    paths = _paths(args)
    action = getattr(args, "action", "run") or "run"
    if action == "start":
        return _start(args, paths)
    if action == "stop":
        return _stop(args, paths)
    if action == "status":
        return _status(args, paths)
    if action == "pair":
        return _pair(args, paths)
    return _foreground(args, paths)


def _foreground(args: argparse.Namespace, paths: WorksPaths) -> int:
    try:
        import uvicorn  # noqa: F401
    except ImportError as exc:  # pragma: no cover - install hint
        raise ConfigError("the daemon needs the server extra: uv sync --extra server") from exc
    if args.host not in LOOPBACK and not args.allow_remote:
        raise ConfigError(
            f"refusing to bind {args.host!r}; pass --allow-remote for a non-loopback address"
        )
    trusted = _trusted_hosts(args)
    from works.interfaces.api.app import create_app
    from works.interfaces.api.wiring import build_state

    if args.write:
        existing = daemons.current_daemon(paths)
        if existing is not None:
            raise ConfigError(
                f"another writable daemon already owns {paths.root}; "
                "open it with `works daemon status --write`"
            )
    open_lan = bool(getattr(args, "open_lan", False))
    state = build_state(paths, writable=args.write, open_lan=open_lan)
    if _requires_read_auth(args) and not state.security.permissions_ok:
        raise ConfigError(
            "a remote bind requires private permissions on .works/state; "
            "fix the ACL on the home or use a loopback daemon behind a tunnel"
        )
    app = create_app(
        state=state,
        trusted_hosts=trusted,
        require_auth=_requires_read_auth(args) and not open_lan,
        scheduler_loop=bool(args.write),
    )
    if open_lan:
        print(
            "WARNING: open LAN mode - anyone who can reach this port can read and write. "
            "Use only on a network you trust.",
            flush=True,
        )
    if args.write:
        info = daemons.current_info(paths, host=args.host, port=args.port)
        print(f"openJiuwen Works daemon (read-write): {_bootstrap_url(info)}", flush=True)
    else:
        print(
            f"openJiuwen Works daemon (read-only): http://{args.host}:{args.port}/",
            flush=True,
        )
    with contextlib.suppress(KeyboardInterrupt):
        run_server(
            app,
            state,
            host=args.host,
            port=args.port,
            write=args.write,
            log_level="info",
        )
    return 0


def _start(args: argparse.Namespace, paths: WorksPaths) -> int:
    if args.host not in LOOPBACK and not args.allow_remote:
        raise ConfigError(
            f"refusing to bind {args.host!r}; pass --allow-remote for a non-loopback address"
        )
    _trusted_hosts(args)
    if bool(getattr(args, "open_lan", False)) and not args.json:
        print(
            "WARNING: open LAN mode - anyone who can reach this port can read and write.",
            flush=True,
        )
    existing = daemons.current_daemon(paths)
    if existing is not None:
        _report(existing, write=args.write, json=args.json, started=False)
        return 0
    info = daemons.start_daemon(
        paths,
        host=args.host,
        port=args.port,
        write=args.write,
        trusted_hosts=tuple(getattr(args, "trusted_host", None) or ()),
        allow_remote=bool(getattr(args, "allow_remote", False)),
        open_lan=bool(getattr(args, "open_lan", False)),
    )
    _report(info, write=args.write, json=args.json, started=True)
    return 0


def _stop(args: argparse.Namespace, paths: WorksPaths) -> int:
    try:
        info = daemons.stop_daemon(paths)
    except NotFoundError as exc:
        if args.json:
            _emit({"running": False, "stopped": False})
        else:
            print(f"daemon is not running: {exc}")
        return 0
    if args.json:
        _emit({"running": False, "stopped": True, "pid": info.pid})
    else:
        print(f"stopped daemon {info.pid} for {info.home}")
    return 0


def _pair(args: argparse.Namespace, paths: WorksPaths) -> int:
    from works.interfaces.cli.daemon_client import DaemonClient

    info = daemons.current_daemon(paths)
    if info is None:
        raise ConfigError(f"no daemon is running for {paths.root}")
    client = DaemonClient(info)
    body = client.post("/api/v1/admin/pair", {"label": args.label})
    code = str(body.get("code") or "")
    if not code:
        raise ConfigError("the daemon did not return a pairing code")
    url = f"{info.base_url}/api/v1/pair"
    if args.json:
        _emit({**body, "url": url})
    else:
        print(f"pairing code: {code}")
        print(f"expires in {body.get('expires_in', 0)}s; post it to {url}")
    return 0


def _status(args: argparse.Namespace, paths: WorksPaths) -> int:
    info = daemons.current_daemon(paths)
    if info is None:
        if args.json:
            _emit({"running": False})
        else:
            print(f"no daemon is running for {paths.root}")
        return EXIT_NOT_FOUND
    _report(info, write=args.write, json=args.json, started=False)
    return 0


def _report(info: daemons.DaemonInfo, *, write: bool, json: bool, started: bool) -> None:
    payload = _payload(info, write=write)
    if json:
        _emit(payload)
        return
    verb = "started" if started else "running"
    print(f"daemon {verb}: {payload['url']}")
    log = Path(info.home) / ".works" / "state" / "daemon.log"
    print(f"pid {info.pid} · home {info.home} · log {log}")
