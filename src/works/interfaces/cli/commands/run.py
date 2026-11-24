"""CLI command group."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from works.domain.errors import (
    EXIT_BLOCKED,
    EXIT_STATE,
    ConfigError,
    PolicyError,
    WorksError,
)
from works.interfaces.cli.commands.common import _emit, _is_ci, _queue
from works.interfaces.cli.commands.wiring import _supervisor


def cmd_run(args: argparse.Namespace) -> int:
    import asyncio

    from works.domain.records import StopReason, TaskState

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

    if args.trace is None and not args.live and not getattr(args, "swarm", False):
        raise ConfigError(
            "no builder configured: pass --trace PATH for a recorded run, "
            "--live for the OpenJiuwen harness, or --swarm for JiuwenSwarm; "
            "or save a builder in Settings"
        )

    task = _queue(args).load(args.task_id)
    repository = Path(task.repo)
    if args.live:
        from works.application.execution.readiness import assess

        report = assess(repository, run_commands=True)
        _queue(args).append(
            task.id,
            "readiness.checked",
            {
                "status": report.status,
                "passed": report.passed,
                "failed": report.failed,
                "total": report.total,
            },
        )
        if report.status == "fail":
            failed = ", ".join(check.id for check in report.checks if check.status == "fail")
            raise PolicyError(
                f"readiness is red ({failed}); add .works/readiness.yaml "
                "and run `works readiness` before automation"
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


def cmd_dispatch(args: argparse.Namespace) -> int:
    import asyncio
    import time

    from works.domain.records import TaskState

    queue = _queue(args)
    scenarios = Path(args.scenarios) if args.scenarios else None
    quarantine = Path(args.quarantine) if args.quarantine else None
    while True:
        ready = [task for task in queue.list_tasks() if task.state is TaskState.QUEUED][
            : args.limit
        ]
        if not ready:
            if args.watch:
                time.sleep(args.interval)
                continue
            if args.json:
                _emit({"runs": [], "selected": 0})
            else:
                print("No ready tasks. Mira is watching the queue.")
            return 0
        supervisor = _supervisor(args)
        records: list[dict[str, Any]] = []
        blocked = False
        for task in ready:
            try:
                record = asyncio.run(
                    supervisor.run(
                        task.id,
                        approve_plan=args.approve_plan,
                        scenario_set=scenarios,
                        quarantine=quarantine,
                    )
                )
                records.append({"task_id": task.id, "run": record.model_dump(mode="json")})
                blocked = blocked or record.state is TaskState.BLOCKED
            except WorksError as exc:
                records.append(
                    {
                        "task_id": task.id,
                        "error": {"code": exc.code, "message": str(exc)},
                    }
                )
                blocked = True
        if args.json:
            _emit({"runs": records, "selected": len(ready)})
        else:
            for item in records:
                if "run" in item:
                    run = item["run"]
                    print(
                        f"{item['task_id']}: {run['state']} ({run['stop_reason']}) · "
                        f"{run['duration_ms']} ms · {run['tokens']} tokens"
                    )
                else:
                    error = item["error"]
                    print(f"{item['task_id']}: {error['code']} — {error['message']}")
        if not args.watch:
            return 8 if blocked else 0


def cmd_wait(args: argparse.Namespace) -> int:
    from datetime import datetime

    from works.domain.records import TaskState

    next_by_kind = {
        "review": TaskState.RELEASING,
        "ci": TaskState.WAITING_DEPLOY,
        "deploy": TaskState.RELEASED,
    }
    deadline = datetime.fromisoformat(args.deadline) if args.deadline else None
    next_state = TaskState(args.next) if args.next else next_by_kind[args.on]
    default = TaskState(args.default) if args.default else TaskState.BLOCKED
    event = _queue(args).wait(
        args.task_id,
        on=args.on,
        wake_on=args.wake_on,
        next_state=next_state,
        deadline=deadline,
        default=default,
    )
    task = _queue(args).load(args.task_id)
    if args.json:
        _emit({"event": event.model_dump(mode="json"), "task": task.model_dump(mode="json")})
    else:
        print(
            f"{task.id} is {task.state.value}, waiting for {task.wake_on} "
            f"(next: {next_state.value})"
        )
    return 0


def cmd_wake(args: argparse.Namespace) -> int:
    event = _queue(args).wake(args.task_id, args.event)
    task = _queue(args).load(args.task_id)
    if args.json:
        _emit({"event": event.model_dump(mode="json"), "task": task.model_dump(mode="json")})
    else:
        print(f"{task.id} woke on {args.event}: {task.state.value}")
    return 0
