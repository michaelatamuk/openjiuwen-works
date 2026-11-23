"""CLI command group."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from works.domain.errors import (
    ConfigError,
)
from works.interfaces.cli.commands.common import _emit, _paths

if TYPE_CHECKING:
    pass


def cmd_ui(args: argparse.Namespace) -> int:
    import webbrowser

    from works.interfaces.api.server import serve

    if args.write and args.read_only:
        raise ConfigError("use either --write or --read-only, not both")
    server = serve(_paths(args), host=args.host, port=args.port, write=args.write)
    address = server.server_address
    host = str(address[0])
    port = int(address[1])
    url = f"http://{host}:{port}/"
    mode = "read-write" if args.write else "read-only"
    if args.json:
        _emit({"url": url, "readonly": not args.write, "write": bool(args.write)})
    else:
        print(f"openJiuwen Works {mode} preview: {url}")
        print("Press Ctrl+C to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0
