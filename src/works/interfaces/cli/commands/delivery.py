"""CLI command group."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING

from works.domain.errors import (
    EXIT_BLOCKED,
    EXIT_OK,
    ConfigError,
)
from works.interfaces.cli.commands.common import _emit, _paths

if TYPE_CHECKING:
    pass


def cmd_release(args: argparse.Namespace) -> int:
    from works.application.delivery.release import release_packet

    packet = release_packet(_paths(args), args.task_id)
    if args.json:
        _emit(packet.as_dict())
    else:
        print(f"Release packet for {packet.task_id}")
        print(f"  run:    {packet.run_id or '-'}")
        print(f"  commit: {packet.commit or '-'}")
        print(f"  proof:  {packet.proof_sha256 or '-'}")
        print(f"  ready:  {'yes' if packet.ready else 'no'}")
        for blocker in packet.blockers:
            print(f"  blocker: {blocker}")
        if packet.released:
            print("  released: yes; delivery is the next step (`works deliver`)")
        else:
            print("  released: no; a person opens gate 2 (`works approve --gate release`)")
    return EXIT_OK if packet.ready else EXIT_BLOCKED


def cmd_deliver(args: argparse.Namespace) -> int:
    from works.application.delivery.deliver import deliver

    delivery = deliver(
        _paths(args),
        args.task_id,
        remote=args.remote,
        provider=args.provider,
        tracker=args.tracker,
        dry_run=args.dry_run,
        base_branch=args.base,
    )
    if args.json:
        _emit(delivery.as_dict())
    else:
        state = "dry run" if delivery.dry_run else "delivered"
        print(f"{state}: {delivery.task_id} -> {delivery.branch} ({delivery.commit})")
        if delivery.pr_url:
            print(f"  pull request: {delivery.pr_url}")
        if delivery.comment_url:
            print(f"  source comment: {delivery.comment_url}")
        for note in delivery.notes:
            print(f"  {note}")
    return 0


def cmd_deploy(args: argparse.Namespace) -> int:
    from works.application.delivery.deploy import deploy

    deployment = deploy(
        _paths(args),
        args.task_id,
        command=args.command,
        environment=args.environment,
        dry_run=args.dry_run,
        force=args.force,
    )
    if args.json:
        _emit(deployment.as_dict())
    else:
        state = "dry run" if deployment.dry_run else deployment.status
        print(f"{state}: {deployment.task_id} {deployment.commit} -> {deployment.environment}")
        if deployment.output_tail:
            print(deployment.output_tail)
        for note in deployment.notes:
            print(f"  {note}")
    return 0 if deployment.status in ("deployed", "dry_run") else EXIT_BLOCKED


def cmd_confirm(args: argparse.Namespace) -> int:
    from works.application.delivery.confirm import confirm
    from works.application.execution.preview import PreviewScript

    command: str | list[str] | None = args.command
    if isinstance(command, str) and command.lstrip().startswith("["):
        try:
            parsed = json.loads(command)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"--command is not a JSON array: {exc}") from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ConfigError("--command must be a JSON array of strings")
        command = parsed
    preview = PreviewScript.from_path(Path(args.preview)) if args.preview else None
    result = confirm(
        _paths(args),
        args.task_id,
        url=args.url,
        command=command,
        preview=preview,
        provider=args.provider,
        tracker=args.tracker,
        close_issue=args.close,
        force=args.force,
    )
    if args.json:
        _emit(result.as_dict())
    else:
        verdict = "confirmed" if result.ok else "failed"
        print(f"{verdict}: {result.task_id} at {result.commit} ({result.target})")
        for note in result.notes:
            print(f"  {note}")
        if result.comment_url:
            print(f"  source comment: {result.comment_url}")
    return 0 if result.ok else EXIT_BLOCKED
