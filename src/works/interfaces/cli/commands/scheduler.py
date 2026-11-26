"""`scheduler` commands: inspect, pause, resume, enable and run one tick."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, cast

from works.application.scheduling.loop import Scheduler
from works.application.scheduling.policy import load_policy, policy_path, set_enabled
from works.domain.errors import EXIT_BLOCKED, ConfigError
from works.interfaces.cli.commands.common import _emit, _paths
from works.interfaces.cli.commands.wiring import _supervisor

if TYPE_CHECKING:
    from works.application.supervisor import Supervisor


def _scheduler(args: argparse.Namespace) -> Scheduler:
    return Scheduler(_paths(args))


def cmd_scheduler_status(args: argparse.Namespace) -> int:
    payload = _scheduler(args).status()
    if args.json:
        _emit(payload)
        return 0
    paused = "paused" if payload["paused"] else "running"
    enabled = "enabled" if payload["enabled"] else "disabled"
    print(f"scheduler: {enabled}, {paused} · tick {payload['tick_seconds']}s")
    print(f"policy: {policy_path(_paths(args))}")
    limits = cast(dict[str, object], payload["limits"])
    print(
        f"slots: {limits['global']} global, {limits['per_repo']} per repo · "
        f"per run ${limits['per_run_usd']:.2f}"
    )
    remaining = limits["remaining_usd"]
    if isinstance(remaining, float):
        print(f"budget left today: ${remaining:.2f}")
    eligible = payload["eligible"]
    if isinstance(eligible, list) and eligible:
        print(f"next: {', '.join(str(item) for item in eligible)}")
    waiting = payload["waiting"]
    if isinstance(waiting, dict) and waiting:
        print("waiting:")
        for task_id, reason in sorted(waiting.items()):
            print(f"  {task_id}: {reason}")
    return 0


def cmd_scheduler_pause(args: argparse.Namespace) -> int:
    scheduler = _scheduler(args)
    scheduler.pause(args.reason or "")
    if args.json:
        _emit({"ok": True, "paused": True, "reason": args.reason or ""})
    else:
        print("scheduler paused; the queue is kept")
    return 0


def cmd_scheduler_resume(args: argparse.Namespace) -> int:
    scheduler = _scheduler(args)
    scheduler.resume()
    if args.json:
        _emit({"ok": True, "paused": False})
    else:
        print("scheduler resumed")
    return 0


def cmd_scheduler_enable(args: argparse.Namespace) -> int:
    path = set_enabled(_paths(args), True)
    if args.json:
        _emit({"ok": True, "enabled": True, "policy": str(path)})
    else:
        print(f"scheduler enabled in {path}")
    return 0


def cmd_scheduler_disable(args: argparse.Namespace) -> int:
    path = set_enabled(_paths(args), False)
    if args.json:
        _emit({"ok": True, "enabled": False, "policy": str(path)})
    else:
        print(f"scheduler disabled in {path}")
    return 0


def _execute(
    supervisor: Supervisor, task_id: str, *, scenarios: Path | None, quarantine: Path | None
) -> None:
    asyncio.run(
        supervisor.run(
            task_id,
            approve_plan=False,
            scenario_set=scenarios,
            quarantine=quarantine,
        )
    )


def cmd_scheduler_tick(args: argparse.Namespace) -> int:
    scheduler = _scheduler(args)
    policy = load_policy(_paths(args))
    if not policy.enabled:
        print(
            f"the scheduler is disabled; run `works scheduler enable` ({policy_path(_paths(args))})"
        )
        return 0
    scenarios = Path(args.scenarios) if args.scenarios else None
    quarantine = Path(args.quarantine) if args.quarantine else None
    execute = None
    if not args.no_run:
        if args.trace is None and not args.live and not getattr(args, "swarm", False):
            raise ConfigError(
                "no builder configured: pass --trace PATH, --live or --swarm, "
                "or use --no-run to only plan the tick"
            )
        supervisor = _supervisor(args)
        execute = lambda task_id: _execute(  # noqa: E731
            supervisor, task_id, scenarios=scenarios, quarantine=quarantine
        )
    result = scheduler.tick(execute=execute, limit=args.limit)
    if result.status == "conflict":
        print(f"another dispatcher is active ({result.error or 'unknown'}); nothing claimed")
        return EXIT_BLOCKED
    if args.json:
        _emit(
            {
                "status": result.status,
                "claimed": result.claimed,
                "skipped": result.skipped,
                "reclaimed": result.reclaimed,
                "order": result.order,
                "executed": result.executed,
            }
        )
    else:
        print(f"tick: {result.status}")
        if result.reclaimed:
            print(f"reclaimed: {', '.join(result.reclaimed)}")
        if result.claimed:
            print(f"claimed: {', '.join(result.claimed)}")
        for item in result.executed:
            print(f"  {item['task_id']}: {item['result']}")
        if result.skipped:
            for task_id, reason in sorted(result.skipped.items()):
                print(f"  {task_id}: {reason}")
    failed = any(item["result"] != "ok" for item in result.executed)
    return EXIT_BLOCKED if failed else 0
