"""CLI command group."""

from __future__ import annotations

import argparse
import json
import os
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

if TYPE_CHECKING:
    from works.application.supervisor import Supervisor


def _planner_for(
    paths: Any,
    settings: Any,
    args: argparse.Namespace,
    flow_name: str,
    *,
    mode: str | None = None,
    prompt_name: str | None = None,
) -> tuple[str, Any, Any]:
    """Build the planner and deep-mode critic selected by Settings."""
    selected = (mode or settings.planner_mode).lower()
    if selected == "deterministic":
        return selected, None, None
    from works.adapters.harness.openjiuwen.builder import (
        default_base,
        default_cli,
        default_key,
        default_model,
    )
    from works.adapters.harness.openjiuwen.planner import HarnessCritic, HarnessPlanner

    base_url = getattr(args, "model_base", None) or default_base()
    prompt_dir = paths.flows / flow_name / "prompts"
    resolved_prompt = prompt_name or ("plan-spec.md" if selected == "spec" else "plan.md")
    try:
        planner = HarnessPlanner(
            provider=settings.resolved_planner_provider,
            model=settings.planner_model or getattr(args, "model", None) or default_model(),
            base_url=base_url,
            api_key=default_key(),
            prompt_path=prompt_dir / resolved_prompt,
            cli_path=default_cli(),
        )
    except ConfigError:
        if selected not in ("shadow", "auto"):
            raise
        return selected, None, None
    critic = None
    if selected in ("deep", "auto"):
        try:
            critic = HarnessCritic(
                provider=settings.resolved_planner_critic_provider,
                model=settings.planner_critic_model or default_model(),
                base_url=base_url,
                api_key=default_key(),
                prompt_path=prompt_dir / "plan-critique.md",
                cli_path=default_cli(),
            )
        except ConfigError:
            if selected == "deep":
                raise
            critic = None
    return selected, planner, critic


def _supervisor(args: argparse.Namespace) -> Supervisor:
    from works.adapters.harness.base import Harness
    from works.adapters.harness.fake import FakeHarness
    from works.adapters.processes.runner import SubprocessRunner
    from works.adapters.queue.ledger import Ledger
    from works.application.supervisor import Supervisor

    paths = _paths(args)
    from works.application.settings import load_builder_settings, settings_path

    builder_settings = load_builder_settings(paths) if settings_path(paths).exists() else None
    explicit_builder = args.trace is not None or args.live or getattr(args, "swarm", False)
    if not explicit_builder and builder_settings is not None:
        # A saved Settings choice is the default builder. Explicit flags still win per run.
        if builder_settings.runtime == "swarm":
            args.swarm = True
        else:
            args.live = True
    if args.trace is not None and args.live:
        raise ConfigError("use either --trace (recorded) or --live (real model), not both")
    swarm = getattr(args, "swarm", False)
    if swarm and (args.trace is not None or args.live):
        raise ConfigError("use either --swarm, --trace or --live; one builder per run")
    harness: Harness | None = None
    if args.trace is not None:
        harness = FakeHarness(args.trace)
    elif swarm:
        from works.adapters.harness.swarm.harness import SwarmHarness

        swarm_kwargs: dict[str, Any] = {}
        if args.swarm_python:
            swarm_kwargs["python"] = Path(args.swarm_python)
        if args.swarm_home:
            swarm_kwargs["home"] = Path(args.swarm_home)
        swarm_harness = SwarmHarness(**swarm_kwargs)
        diagnostic = swarm_harness.diagnostic()
        if not diagnostic.ok:
            raise ConfigError(f"JiuwenSwarm is not ready: {diagnostic.detail}")
        harness = swarm_harness
    elif args.live:
        from works.adapters.harness.openjiuwen.builder import LiveHarness

        if builder_settings is None:
            builder_settings = load_builder_settings(paths)
        task_id = getattr(args, "task_id", None)
        flow = "fix-issue"
        if task_id:
            flow = _queue(args).load(task_id).flow
        prompt_path = getattr(args, "prompt", None)
        if prompt_path is None:
            candidate = paths.flows / flow / "prompts" / "build.md"
            prompt_path = candidate if candidate.exists() else None
        challenge_path = paths.flows / flow / "prompts" / "challenge.md"
        harness = LiveHarness(
            model=args.model or builder_settings.model,
            verifier_model=builder_settings.verifier_model,
            base_url=args.model_base,
            harness_provider=builder_settings.provider,
            verifier_harness_provider=builder_settings.verifier_provider,
            prompt_path=prompt_path,
            challenge_prompt_path=challenge_path if challenge_path.exists() else None,
        )
    memory = None
    ppma_url = args.ppma or os.environ.get("WORKS_PPMA_URL")
    if ppma_url:
        from works.application.memory.ppma import PpmaMemory

        memory = PpmaMemory(ppma_url, space=args.ppma_space)
    from works.application.execution.verifier import DockerVerifier, Mount, verifier_from_name

    planner = None
    critic = None
    planner_mode = (
        builder_settings.planner_mode if builder_settings is not None else "deterministic"
    )
    if args.trace is not None:
        # A recorded run must stay reproducible; it never calls a planner model.
        planner_mode = "deterministic"
    elif builder_settings is not None:
        task_id = getattr(args, "task_id", None)
        flow_name = _queue(args).load(task_id).flow if task_id else "fix-issue"
        planner_mode, planner, critic = _planner_for(paths, builder_settings, args, flow_name)

    runner = SubprocessRunner()
    verifier_name = getattr(args, "verifier", "local") or "local"
    mounts = (
        Mount(paths.worktrees, "/works/worktrees", read_only=False),
        Mount(paths.scenarios, "/works/scenarios"),
    )
    verifier = verifier_from_name(
        verifier_name,
        runner,
        image=getattr(args, "verifier_image", None),
        mounts=mounts,
    )
    if isinstance(verifier, DockerVerifier) and not verifier.available():
        raise ConfigError(
            "Docker is installed but its daemon is not reachable; "
            "start Docker Desktop or use --verifier local"
        )
    return Supervisor(
        paths=paths,
        queue=_queue(args),
        ledger=Ledger(paths.ledger),
        harness=harness,
        runner=runner,
        memory=memory,
        decision_mode=getattr(args, "decision", None),
        verifier=verifier,
        planner_mode=planner_mode,
        planner=planner,
        critic=critic,
    )


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
