"""`works reproduce` — how to check a repository, and where the checkout comes from."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from works.application.reproduce import detect, env, resolver
from works.interfaces.cli.commands.common import _emit, _paths


def cmd_reproduce(args: argparse.Namespace) -> int:
    if args.action == "checkout":
        if not args.url:
            raise SystemExit("--url is required")
        found = resolver.checkout(_paths(args), args.url, args.ref, offline=args.offline)
        payload: dict[str, Any] = {
            "path": str(found.path),
            "commit": found.commit,
            "ref": found.ref,
        }
        if args.json:
            _emit(payload)
        else:
            print(f"{found.path}\n{found.commit} ({found.ref or 'HEAD'})")
        return 0
    if not args.repo:
        raise SystemExit("--repo is required")
    repo = Path(args.repo).expanduser().resolve()
    if args.action == "detect":
        detection = detect.choose(repo, args.hint)
        detected: dict[str, Any] = (
            {"command": detection.command, "source": detection.source, "reason": detection.reason}
            if detection
            else {"command": [], "source": None, "reason": "no manifest or hint"}
        )
        if args.json:
            _emit(detected)
        else:
            print(" ".join(detected["command"]) if detected["command"] else "no command detected")
            print(detected["reason"])
        return 0
    if args.action == "prepare":
        planned = env.prepare(_paths(args), repo, offline=args.offline)
        prepared: dict[str, Any] = {
            "kind": planned.kind,
            "directory": str(planned.directory),
            "commands": planned.commands,
            "fingerprint": planned.fingerprint,
            "notes": planned.notes,
        }
        if args.json:
            _emit(prepared)
        else:
            print(f"{planned.kind}: {planned.directory}")
            for command in planned.commands:
                print("  " + " ".join(command))
        return 0
    raise SystemExit(f"unknown action {args.action!r}")
