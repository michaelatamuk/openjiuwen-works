"""CLI command group."""

from __future__ import annotations

import argparse
import contextlib
from urllib.parse import quote

from works.domain.errors import ConfigError
from works.interfaces.cli.commands.common import _emit, _paths

LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


def cmd_ui(args: argparse.Namespace) -> int:
    import webbrowser

    try:
        import uvicorn  # noqa: F401
    except ImportError as exc:  # pragma: no cover - install hint
        raise ConfigError("the UI needs the server extra: uv sync --extra server") from exc
    from works.interfaces.api.app import create_app
    from works.interfaces.api.wiring import build_state
    from works.interfaces.cli.commands.daemon import run_server

    if args.write and args.read_only:
        raise ConfigError("use either --write or --read-only, not both")
    if args.host not in LOOPBACK:
        raise ConfigError(f"refusing to bind {args.host!r}; the local UI is loopback-only")
    paths = _paths(args)
    if args.write:
        from works.adapters import daemon as daemons

        if daemons.current_daemon(paths) is not None:
            raise ConfigError(
                f"another writable daemon already owns {paths.root}; "
                "use it instead or stop it with `works daemon stop`"
            )
    state = build_state(paths, writable=args.write)
    app = create_app(state=state)
    url = f"http://{args.host}:{args.port}/"
    if args.write:
        token = state.security.token
        url += f"?bootstrap={quote(token)}"
    mode = "read-write" if args.write else "read-only"
    if args.json:
        _emit({"url": url, "readonly": not args.write, "write": bool(args.write)})
    else:
        print(f"openJiuwen Works {mode} preview: {url}", flush=True)
        print("Press Ctrl+C to stop.", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    with contextlib.suppress(KeyboardInterrupt):
        run_server(
            app,
            state,
            host=args.host,
            port=args.port,
            write=args.write,
            log_level="warning",
        )
    return 0
