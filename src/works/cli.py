"""The first window: a CLI. Standard library only on the startup path.

Every command speaks JSON and has a stable exit code. Heavy modules are imported inside the
command that needs them, so `works --help` and `works status` stay inside the budget.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import WorksPaths
    from .queue import Queue
    from .supervisor import Supervisor

from .errors import (
    EXIT_BLOCKED,
    EXIT_INTERNAL,
    EXIT_POLICY,
    EXIT_STATE,
    ConfigError,
    NotImplementedYet,
    WorksError,
    exit_code_for,
)
from .render import table

DESCRIPTION = "A software factory: one signal in, a released fix out."


def _paths(args: argparse.Namespace) -> WorksPaths:
    from .config import load_paths

    return load_paths(args.home)


def _queue(args: argparse.Namespace) -> Queue:
    from .queue import Queue

    return Queue(_paths(args))


def _emit(payload: dict[str, Any]) -> None:
    print(
        json.dumps(
            {"ok": True, **payload},
            ensure_ascii=False,
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


def cmd_version(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps({"ok": True, "version": "0.0.1"}))
    else:
        print("openjiuwen-works 0.0.1")
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    from .records import Source, SourceKind

    try:
        kind = SourceKind(args.kind)
    except ValueError as exc:
        raise ConfigError(
            f"unknown source kind {args.kind!r}; expected manual, tracker, detector"
        ) from exc
    target = (args.repo or Path.cwd()).expanduser().resolve()
    task, created = _queue(args).submit(
        source=Source(kind=kind, ref=args.ref, title=args.title),
        flow=args.flow,
        product=args.product,
        repo=str(target),
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
    from . import fast

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


def cmd_task(args: argparse.Namespace) -> int:
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


def cmd_approve(args: argparse.Namespace) -> int:
    from .records import TaskState

    if args.gate == "release":
        raise NotImplementedYet("the release gate lands in M3; nothing is published in v0")
    if args.gate != "plan":
        raise ConfigError(f"unknown gate {args.gate!r}; expected plan or release")
    queue = _queue(args)
    task = queue.load(args.task_id)
    if task.state is not TaskState.PLANNING:
        raise ConfigError(
            f"task {args.task_id} is {task.state.value}; the plan gate needs planning"
        )
    queue.transition(args.task_id, TaskState.PLAN_APPROVED)
    queue.append(
        args.task_id,
        "gate.decided",
        {"gate": "plan", "decision": "approved", "by": "cli"},
    )
    updated = queue.load(args.task_id)
    if args.json:
        _emit({"task": updated.model_dump(mode="json")})
    else:
        print(f"plan approved: {args.task_id} is now {updated.state.value}")
    return 0


def _supervisor(args: argparse.Namespace) -> Supervisor:
    from .harness.fake import FakeHarness
    from .ledger import Ledger
    from .runner import SubprocessRunner
    from .supervisor import Supervisor

    paths = _paths(args)
    harness = None
    if args.trace is not None:
        harness = FakeHarness(args.trace)
    return Supervisor(
        paths=paths,
        queue=_queue(args),
        ledger=Ledger(paths.ledger),
        harness=harness,
        runner=SubprocessRunner(),
    )


def cmd_run(args: argparse.Namespace) -> int:
    import asyncio

    from .records import StopReason, TaskState

    scenarios = Path(args.scenarios) if args.scenarios else None
    quarantine = Path(args.quarantine) if args.quarantine else None
    supervisor = _supervisor(args)
    if args.dry_run:
        payload = supervisor.plan_run(args.task_id, scenario_set=scenarios)
        if args.json:
            _emit(payload)
        else:
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0

    if args.trace is None:
        raise ConfigError(
            "no harness configured: pass --trace PATH to replay a recorded trace "
            "(the live openjiuwen adapter lands in M1)"
        )

    if not args.approve_plan and not _is_ci() and sys.stdin.isatty():
        preview = supervisor.plan_run(args.task_id, scenario_set=scenarios)
        print(json.dumps(preview, indent=2, ensure_ascii=False, default=str))
        answer = input("Approve this plan and build? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("plan not approved; the task stays in planning")
            return EXIT_STATE
        args.approve_plan = True

    record = asyncio.run(
        supervisor.run(
            args.task_id,
            approve_plan=args.approve_plan,
            scenario_set=scenarios,
            quarantine=quarantine,
        )
    )
    if args.json:
        _emit({"run": record.model_dump(mode="json")})
    else:
        print(
            f"run {record.run_id}: {record.state.value} ({record.stop_reason.value}) · "
            f"{record.duration_ms} ms · {record.tokens} tokens · ${record.usd:.4f}"
        )
        if record.evidence_md:
            print(f"proof: {record.evidence_md}")
    if record.stop_reason is StopReason.NEEDS_PLAN_APPROVAL:
        return EXIT_STATE
    if record.state is TaskState.BLOCKED:
        return EXIT_BLOCKED
    return 0


def cmd_policy_check(args: argparse.Namespace) -> int:
    from .flow import PathsSpec, find_flow, load_flow
    from .policy import check_paths

    spec = PathsSpec()
    if args.flow is not None:
        spec = load_flow(find_flow(_paths(args).flows, args.flow)).paths
    violations = check_paths(args.paths, spec)
    if args.json:
        _emit(
            {
                "allowed": not violations,
                "violations": [violation.model_dump() for violation in violations],
            }
        )
    elif violations:
        for violation in violations:
            print(f"{violation.path}: {violation.reason}", file=sys.stderr)
    else:
        print(f"{len(args.paths)} path(s) allowed")
    return EXIT_POLICY if violations else 0


def cmd_ledger(args: argparse.Namespace) -> int:
    from .ledger import Ledger

    rows = Ledger(_paths(args).ledger).rows()
    if args.json:
        _emit({"rows": [row.model_dump(mode="json") for row in rows]})
        return 0
    rendered = [
        (
            row.ts.isoformat(timespec="seconds"),
            row.task_id,
            row.run_id or "-",
            row.state.value,
            row.verdict or "-",
            row.tokens if row.tokens is not None else "-",
            f"{row.usd:.4f}" if row.usd is not None else "-",
        )
        for row in rows
    ]
    print(table(("ts", "task", "run", "state", "verdict", "tokens", "usd"), rendered))
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    from .schema import all_schemas

    payload = all_schemas()
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print(f"Schemas (v{payload['schema_version']})")
    for name, model_schema in payload["schemas"].items():
        print(f"  {name}: {model_schema.get('title', '')}")
    print("Use `works schema --json` for the full documents.")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import failed, run_checks

    paths = _paths(args)
    repo = (args.repo or Path.cwd()).expanduser().resolve()
    results = run_checks(paths, repo=repo)
    if args.json:
        _emit({"checks": [result.model_dump() for result in results]})
    else:
        print(
            table(
                ("check", "status", "detail"),
                [(result.name, result.status, result.detail) for result in results],
            )
        )
    return 1 if failed(results) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="works", description=DESCRIPTION)
    parser.add_argument("--home", type=Path, default=None, help="Workspace root")
    sub = parser.add_subparsers(dest="command", required=True)

    version = sub.add_parser("version", help="Print the version")
    version.add_argument("--json", action="store_true")
    version.set_defaults(func=cmd_version)

    submit = sub.add_parser("submit", help="Submit a signal; duplicate sources return one task")
    submit.add_argument("--ref", "-r", required=True, help="Source reference, e.g. GH-42")
    submit.add_argument("--title", "-t", default="", help="One-line title")
    submit.add_argument("--flow", default="fix-issue")
    submit.add_argument("--product", default="openjiuwen")
    submit.add_argument("--repo", type=Path, default=None)
    submit.add_argument("--kind", default="manual", help="manual, tracker or detector")
    submit.add_argument("--json", action="store_true")
    submit.set_defaults(func=cmd_submit)

    status = sub.add_parser("status", help="Show one task or the queue")
    status.add_argument("task_id", nargs="?", default=None)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    task = sub.add_parser("task", help="Print the task projection")
    task.add_argument("task_id")
    task.add_argument("--json", action="store_true")
    task.set_defaults(func=cmd_task)

    trace = sub.add_parser("trace", help="Render the event timeline")
    trace.add_argument("task_id")
    trace.add_argument("--json", action="store_true")
    trace.set_defaults(func=cmd_trace)

    approve = sub.add_parser("approve", help="Approve the plan gate")
    approve.add_argument("task_id")
    approve.add_argument("--gate", default="plan", help="plan or release")
    approve.add_argument("--json", action="store_true")
    approve.set_defaults(func=cmd_approve)

    run = sub.add_parser("run", help="Reproduce, plan, build, check, prove")
    run.add_argument("task_id")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--approve-plan", action="store_true")
    run.add_argument("--scenarios", default=None)
    run.add_argument("--quarantine", default=None)
    run.add_argument("--trace", type=Path, default=None)
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)

    policy = sub.add_parser("policy", help="Path policy")
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    check = policy_sub.add_parser("check", help="Check paths before any command runs")
    check.add_argument("paths", nargs="+")
    check.add_argument("--flow", default=None)
    check.add_argument("--json", action="store_true")
    check.set_defaults(func=cmd_policy_check)

    ledger = sub.add_parser("ledger", help="Read the append-only ledger")
    ledger.add_argument("--json", action="store_true")
    ledger.set_defaults(func=cmd_ledger)

    schema = sub.add_parser("schema", help="Print every persisted schema")
    schema.add_argument("--json", action="store_true")
    schema.set_defaults(func=cmd_schema)

    doctor = sub.add_parser("doctor", help="Check config, git, harness, container, credentials")
    doctor.add_argument("--repo", type=Path, default=None)
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result: int = args.func(args)
        return result
    except WorksError as exc:
        return _fail(exc, as_json=bool(getattr(args, "json", False)))


def main_entry() -> None:
    from .bootstrap import harden_sys_path
    from .logs import configure

    harden_sys_path()
    configure(os.environ.get("WORKS_LOG_LEVEL", "INFO"))
    try:
        raise SystemExit(main())
    except WorksError as exc:
        raise SystemExit(_fail(exc, as_json=False)) from exc
    except SystemExit:
        raise
    except Exception as exc:
        print(f"internal error: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_INTERNAL) from exc


if __name__ == "__main__":
    main_entry()
