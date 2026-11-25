"""CLI entry point."""

from __future__ import annotations

import os
import sys

from works.domain.errors import EXIT_INTERNAL, WorksError
from works.interfaces.cli.commands.common import _fail
from works.interfaces.cli.parser import build_parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result: int = args.func(args)
        return result
    except WorksError as exc:
        return _fail(exc, as_json=bool(getattr(args, "json", False)))


def main_entry() -> None:
    from works.config.bootstrap import harden_sys_path
    from works.config.logging import configure

    harden_sys_path()
    configure(os.environ.get("WORKS_LOG_LEVEL", "INFO"))
    from works.application.observability.tracing import configure_tracing

    configure_tracing()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        raise SystemExit(main())
    except WorksError as exc:
        raise SystemExit(_fail(exc, as_json=False)) from exc
    except SystemExit:
        raise
    except Exception as exc:
        print(f"internal error: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_INTERNAL) from exc
