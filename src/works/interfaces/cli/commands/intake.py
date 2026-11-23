"""CLI command group."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from works.domain.errors import (
    EXIT_BLOCKED,
    ConfigError,
)
from works.interfaces.cli.commands.common import _emit, _paths, _queue

if TYPE_CHECKING:
    pass


def cmd_source_github(args: argparse.Namespace) -> int:
    from works.application.intake.products import resolve_repo
    from works.application.intake.sources import github_issues, ingest_issues

    issues = github_issues(args.repository, label=args.label, limit=args.limit)
    repo = resolve_repo(_paths(args), args.product, args.repo)
    created = ingest_issues(_queue(args), product=args.product, repo=str(repo), issues=issues)
    fresh = sum(1 for _, was_created in created if was_created)
    if args.json:
        _emit(
            {
                "source": "github",
                "found": len(issues),
                "created": fresh,
                "tasks": [task.id for task, _ in created],
            }
        )
    else:
        print(f"github: {len(issues)} issue(s), {fresh} new")
    return 0


def cmd_source_jira(args: argparse.Namespace) -> int:
    from works.application.intake.products import resolve_repo
    from works.application.intake.sources import ingest_issues, jira_issues

    issues = jira_issues(args.url, args.jql, limit=args.limit)
    repo = resolve_repo(_paths(args), args.product, args.repo)
    created = ingest_issues(_queue(args), product=args.product, repo=str(repo), issues=issues)
    fresh = sum(1 for _, was_created in created if was_created)
    if args.json:
        _emit(
            {
                "source": "jira",
                "found": len(issues),
                "created": fresh,
                "tasks": [task.id for task, _ in created],
            }
        )
    else:
        print(f"jira: {len(issues)} issue(s), {fresh} new")
    return 0


def cmd_source_detector(args: argparse.Namespace) -> int:
    from pathlib import Path

    from works.application.intake.detectors import (
        fetch_alerts,
        ingest_alerts,
        ingest_named,
        read_alert_file,
    )
    from works.application.intake.products import resolve_repo

    if args.name:
        created = ingest_named(_paths(args), args.name)[: args.limit]
    else:
        if not args.product:
            raise ConfigError("--product is required unless --name selects a configured detector")
        if args.file:
            alerts = read_alert_file(Path(args.file).expanduser())
        elif args.url:
            alerts = fetch_alerts(args.url)
        else:
            raise ConfigError("pass --name, --file or --url")
        alerts = alerts[: args.limit]
        repo = resolve_repo(_paths(args), args.product, args.repo)
        created = ingest_alerts(_queue(args), product=args.product, repo=str(repo), alerts=alerts)
    fresh = sum(1 for _, was_created in created if was_created)
    if args.json:
        _emit(
            {
                "source": "detector",
                "found": len(created),
                "created": fresh,
                "tasks": [task.id for task, _ in created],
            }
        )
    else:
        print(f"detector: {len(created)} alert(s), {fresh} new")
    return 0


def cmd_swarm_doctor(args: argparse.Namespace) -> int:
    from works.adapters.harness.swarm.harness import preflight

    diagnostic = preflight(
        Path(args.python) if args.python else None,
        home=Path(args.home) if args.home else None,
    )
    body = {
        "ok": diagnostic.ok,
        "detail": diagnostic.detail,
        "argv": list(diagnostic.argv),
        "exit_code": diagnostic.exit_code,
        "output_tail": diagnostic.output_tail,
        "contract": "works.swarm.v1",
    }
    if args.json:
        _emit(body)
    else:
        print(f"jiuwenswarm: {'ready' if diagnostic.ok else 'not ready'}")
        print(f"  {diagnostic.detail}")
        if diagnostic.output_tail:
            print(f"  last output: {diagnostic.output_tail}")
    return 0 if diagnostic.ok else EXIT_BLOCKED
