"""Shared CLI runtime helpers."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import TYPE_CHECKING, Any

from works.domain.errors import WorksError, exit_code_for

if TYPE_CHECKING:
    from works.adapters.queue.store import Queue
    from works.config.paths import WorksPaths

DESCRIPTION = "A software factory: one signal in, a released fix out."


def _paths(args: argparse.Namespace) -> WorksPaths:
    from works.config.paths import load_paths

    return load_paths(args.home)


def _queue(args: argparse.Namespace) -> Queue:
    from works.adapters.queue.store import Queue

    return Queue(_paths(args))


def _emit(payload: dict[str, Any]) -> None:
    print(
        json.dumps(
            {"ok": True, **payload},
            ensure_ascii=True,
            default=str,
            separators=(",", ":"),
        )
    )


def _fail(exc: WorksError, *, as_json: bool) -> int:
    if as_json:
        print(
            json.dumps(
                {"ok": False, "error": {"code": exc.code, "message": str(exc)}},
                ensure_ascii=False,
            )
        )
    else:
        print(f"{exc.code}: {exc}", file=sys.stderr)
    return exit_code_for(exc)


def _is_ci() -> bool:
    return any(os.environ.get(name) for name in ("CI", "GITHUB_ACTIONS", "TF_BUILD"))
