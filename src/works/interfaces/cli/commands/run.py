"""CLI command group."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from works.domain.errors import (
    EXIT_BLOCKED,
    EXIT_STATE,
    ConfigError,
    PolicyError,
    WorksError,
)
from works.interfaces.cli.commands.common import _emit, _is_ci, _paths, _queue
from works.interfaces.cli.commands.wiring import _supervisor

if TYPE_CHECKING:
    from works.interfaces.cli.daemon_client import DaemonClient


def _resolve_path(value: str | None) -> str | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return str(path if path.is_absolute() else path.resolve())


def _run_options(args: argparse.Namespace) -> dict[str, str | bool | None]:
    return {
        "approve_plan": bool(args.approve_plan),
        "scenarios": _resolve_path(args.scenarios),
        "quarantine": _resolve_path(args.quarantine),
        "trace": _resolve_path(str(args.trace)) if args.trace else None,
        "live": bool(args.live),
        "swarm": bool(getattr(args, "swarm", False)),
        "model": args.model,
        "model_base": args.model_base,
        "prompt": _resolve_path(str(args.prompt)) if args.prompt else None,
        "ppma": args.ppma,
        "ppma_space": args.ppma_space,
        "decision": args.decision,
        "verifier": args.verifier,
        "verifier_image": args.verifier_image,
    }


def _daemon_client(args: argparse.Namespace) -> DaemonClient:
    from works.adapters import daemon as daemons
    from works.interfaces.cli.daemon_client import DaemonClient

    paths = _paths(args)
    info = daemons.current_daemon(paths)
    if info is None:
        raise ConfigError(
            f"no daemon is running for {paths.root}; start one with `works daemon start --write`"
        )
    return DaemonClient(info)


def _daemon_job_id(accepted: dict[str, Any]) -> str:
    job = accepted.get("job")
    job_id = job.get("id") if isinstance(job, dict) else None
    if not job_id:
        raise ConfigError("the daemon did not return a job id")
    return str(job_id)


def _refuse_when_daemon_owns(args: argparse.Namespace) -> None:
    from works.adapters import daemon as daemons

    paths = _paths(args)
    if daemons.current_daemon(paths) is not None:
        raise ConfigError(
            f"a writable daemon owns {paths.root}; use --daemon or `works daemon stop`"
        )


def _run_exit_code(record: dict[str, Any]) -> int:
    if record.get("stop_reason") == "needs_plan_approval":
        return EXIT_STATE
    if record.get("state") == "blocked":
        return EXIT_BLOCKED
    return 0


def _print_run(record: dict[str, Any]) -> None:
    print(
        f"run {record.get('run_id')}: {record.get('state')} "
        f"({record.get('stop_reason')}) · {record.get('duration_ms')} ms · "
        f"{record.get('tokens')} tokens · ${float(record.get('usd') or 0):.4f}"
    )
    if record.get("evidence_md"):
        print(f"proof: {record['evidence_md']}")


def _job_result(job: dict[str, Any]) -> dict[str, Any]:
    result = job.get("result")
    return result if isinstance(result, dict) else {}


def _run_via_daemon(args: argparse.Namespace) -> int:
    client = _daemon_client(args)
    accepted = client.post("/api/v1/runs", {"task_id": args.task_id, **_run_options(args)})
    job = client.wait(_daemon_job_id(accepted))
    payload = _job_result(job)
    run_payload = payload.get("run")
    record: dict[str, Any] = run_payload if isinstance(run_payload, dict) else {}
    if args.json:
        _emit({"run": record})
    else:
        _print_run(record)
    return _run_exit_code(record)


def _dispatch_via_daemon(args: argparse.Namespace) -> int:
    if args.watch:
        raise ConfigError("dispatch --watch is standalone only; the daemon owns runs")
    client = _daemon_client(args)
    accepted = client.post("/api/v1/dispatch", {"limit": args.limit, **_run_options(args)})
    job = client.wait(_daemon_job_id(accepted))
    payload = _job_result(job)
    raw_records = payload.get("runs")
    records: list[dict[str, Any]] = (
        [item for item in raw_records if isinstance(item, dict)]
        if isinstance(raw_records, list)
        else []
    )
    selected = payload.get("selected")
    selected = selected if isinstance(selected, int) else len(records)
    if args.json:
        _emit({"runs": records, "selected": selected})
    else:
        if not records:
            print("No ready tasks. Mira is watching the queue.")
        for item in records:
            run = item.get("run")
            if isinstance(run, dict):
                print(
                    f"{item.get('task_id')}: {run.get('state')} "
                    f"({run.get('stop_reason')}) · {run.get('duration_ms')} ms · "
                    f"{run.get('tokens')} tokens"
                )
            else:
                error = item.get("error")
                if isinstance(error, dict):
                    print(f"{item.get('task_id')}: {error.get('code')} — {error.get('message')}")
    blocked = any(
        "error" in item
        or (isinstance(item.get("run"), dict) and item["run"].get("state") == "blocked")
        for item in records
    )
    return EXIT_BLOCKED if blocked else 0


def cmd_run(args: argparse.Namespace) -> int:
    import asyncio

    from works.domain.records import StopReason, TaskState

    if getattr(args, "daemon", False) and not args.dry_run:
        return _run_via_daemon(args)
    if not args.dry_run:
        _refuse_when_daemon_owns(args)

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

    if getattr(args, "daemon", False):
        return _dispatch_via_daemon(args)
    _refuse_when_daemon_owns(args)

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
