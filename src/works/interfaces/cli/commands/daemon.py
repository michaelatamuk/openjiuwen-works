"""CLI command group."""

from __future__ import annotations

import argparse

from works.domain.errors import ConfigError
from works.interfaces.cli.commands.common import _paths

LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


def cmd_daemon(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - exercised by the install hint
        raise ConfigError("the daemon needs the server extra: uv sync --extra server") from exc
    if args.host not in LOOPBACK and not args.allow_remote:
        raise ConfigError(
            f"refusing to bind {args.host!r}; pass --allow-remote for a non-loopback address"
        )
    from works.interfaces.api.app import create_app

    app = create_app(_paths(args), writable=args.write)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0
