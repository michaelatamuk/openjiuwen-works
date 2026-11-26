"""CLI command group."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING

from works.domain.errors import ConfigError
from works.domain.records import TaskState
from works.domain.state import TERMINAL
from works.interfaces.cli.commands.common import _emit, _paths, _queue
from works.interfaces.cli.render import table

if TYPE_CHECKING:
    pass


def cmd_version(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps({"ok": True, "version": "0.0.1"}))
    else:
        print("openjiuwen-works 0.0.1")
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    from works.application.intake.products import resolve_repo
    from works.domain.records import Source, SourceKind, TaskKind

    try:
        kind = SourceKind(args.kind)
    except ValueError as exc:
        raise ConfigError(
            f"unknown source kind {args.kind!r}; expected manual, tracker, detector"
        ) from exc
    try:
        task_kind = TaskKind(args.task_kind)
    except ValueError as exc:
        raise ConfigError(
            f"unknown task kind {args.task_kind!r}; expected fix or check-change"
        ) from exc
    target = resolve_repo(_paths(args), args.product, args.repo)
    task, created = _queue(args).submit(
        source=Source(kind=kind, ref=args.ref, title=args.title),
        flow=args.flow,
        product=args.product,
        repo=str(target),
        task_kind=task_kind,
    )
    body = {"task": task.model_dump(mode="json"), "created": created}
    if args.json:
        _emit(body)
    else:
        status = "created" if created else "already existed"
        print(
            f"{status}: {task.id} ({task.state.value}, "
            f"source {task.source.kind.value}:{task.source.ref})"
        )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from works.adapters.queue import fast_read as fast

    paths = _paths(args)
    if args.task_id:
        item = fast.summary(paths.queue, args.task_id)
        if item is None:
            task = _queue(args).load(args.task_id)
            item = task.model_dump(mode="json")
        body = {
            "task": item,
            "owner": fast.owner(paths.queue, args.task_id),
            "events": fast.event_count(paths.queue, args.task_id),
        }
        if args.json:
            _emit(body)
        else:
            print(json.dumps(item, indent=2, ensure_ascii=False))
            print(f"owner: {body['owner'] or '-'} · events: {body['events']}")
        return 0

    items = fast.summaries(paths.queue)
    if items is None:
        queue = _queue(args)
        items = [task.model_dump(mode="json") for task in queue.list_tasks()]
        queue.rebuild_index()
    if args.json:
        _emit({"tasks": items})
        return 0
    if not items:
        print("No tasks yet. Mira is watching the queue.")
        return 0
    rows = [
        (
            item.get("id", ""),
            item.get("state", ""),
            item.get("flow", ""),
            f"{item.get('source', {}).get('kind', '')}:{item.get('source', {}).get('ref', '')}",
            item.get("attempts", 0),
            fast.owner(paths.queue, str(item.get("id", ""))) or "-",
        )
        for item in items
    ]
    print(table(("id", "state", "flow", "source", "attempts", "owner"), rows))
    return 0


def _merge_task(args: argparse.Namespace) -> int:
    into = str(args.merge_into or "").strip()
    if not into:
        raise ConfigError("--merge-into needs a target task id")
    if into == args.task_id:
        raise ConfigError("a task cannot be merged into itself")
    paths = _paths(args)
    from works.adapters import daemon as daemons

    info = daemons.current_daemon(paths)
    if info is not None:
        from works.interfaces.cli.daemon_client import DaemonClient

        body = DaemonClient(info).post(f"/tasks/{args.task_id}/merge", {"into": into})
        if args.json:
            _emit(body)
        else:
            print(f"merged {args.task_id} into {into}")
        return 0
    queue = _queue(args)
    task = queue.load(args.task_id)
    target = queue.load(into)
    if target.state in TERMINAL:
        raise ConfigError(f"cannot merge into {into}: it is {target.state.value}")
    if task.state not in TERMINAL:
        queue.append(args.task_id, "task.merged", {"into": into})
        queue.transition(args.task_id, TaskState.BLOCKED)
    if args.json:
        _emit({"ok": True, "merged": args.task_id, "into": into})
    else:
        print(f"merged {args.task_id} into {into}")
    return 0


def cmd_retry(args: argparse.Namespace) -> int:
    from dataclasses import asdict

    from works.application.reporter import record_reply

    reply = record_reply(
        _paths(args),
        task_id=args.task_id,
        text=args.note,
        author="cli",
        source="cli",
    )
    if args.json:
        _emit(asdict(reply))
    elif reply.reopened:
        print(f"reopened {reply.task_id}; the queue can pick it up again")
    else:
        print(f"not reopened: {reply.reason}")
    return 0 if reply.task_id else 1


def cmd_task(args: argparse.Namespace) -> int:
    if getattr(args, "merge_into", None):
        return _merge_task(args)
    queue = _queue(args)
    task = queue.load(args.task_id)
    events = queue.events(args.task_id)
    queue.verify_projection(args.task_id)
    body = {"task": task.model_dump(mode="json"), "events": len(events)}
    if args.json:
        _emit(body)
    else:
        print(json.dumps(body, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    events = _queue(args).events(args.task_id)
    if args.json:
        _emit(
            {
                "task_id": args.task_id,
                "events": [event.model_dump(mode="json") for event in events],
            }
        )
        return 0
    rows = []
    for event in events:
        summary = ", ".join(f"{key}={value}" for key, value in sorted(event.data.items()))
        rows.append((event.seq, event.ts.isoformat(), event.type, summary[:120]))
    print(table(("seq", "ts", "type", "data"), rows))
    return 0


def cmd_finding_add(args: argparse.Namespace) -> int:
    from works.domain.records import Finding

    try:
        confidence = float(args.confidence) if args.confidence is not None else None
    except ValueError as exc:
        raise ConfigError(
            f"confidence must be a number between 0 and 1: {args.confidence}"
        ) from exc
    finding = Finding(
        step=args.step,
        summary=args.summary,
        confidence=confidence,
        uncertainty=args.uncertainty,
        evidence=args.evidence or [],
    )
    _queue(args).append(args.task_id, "finding", finding.model_dump(mode="json"))
    if args.json:
        _emit({"finding": finding.model_dump(mode="json")})
    else:
        print(f"finding recorded for {args.task_id}: {finding.summary}")
    return 0


def cmd_finding_list(args: argparse.Namespace) -> int:
    from works.domain.records import Finding

    events = _queue(args).events(args.task_id)
    findings = [Finding.model_validate(event.data) for event in events if event.type == "finding"]
    if args.json:
        _emit({"findings": [finding.model_dump(mode="json") for finding in findings]})
        return 0
    print(
        table(
            ("step", "finding", "confidence", "uncertainty"),
            [
                (
                    finding.step or "-",
                    finding.summary,
                    "-" if finding.confidence is None else f"{finding.confidence:.2f}",
                    finding.uncertainty or "-",
                )
                for finding in findings
            ],
        )
    )
    return 0
