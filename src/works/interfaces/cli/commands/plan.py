"""CLI command group."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.domain.errors import (
    EXIT_BLOCKED,
    EXIT_POLICY,
    ConfigError,
)
from works.interfaces.cli.commands.common import _emit, _paths
from works.interfaces.cli.commands.wiring import _planner_for


def cmd_plan(args: argparse.Namespace) -> int:
    from works.application.planning.service import PlanStore, plan_markdown

    paths = _paths(args)
    store = PlanStore(paths)
    action = getattr(args, "action", "draft")

    if action in ("show", "lint", "diff", "replan", "alternatives") and not args.task_id:
        raise ConfigError(f"`works plan --action {action}` needs a task id")

    if action == "show":
        plan = store.load(args.task_id, getattr(args, "version", None))
        if args.json:
            _emit(plan.model_dump(mode="json"))
        else:
            print(plan_markdown(plan))
        return 0

    if action == "lint":
        plan = store.load(args.task_id, getattr(args, "version", None))
        validation = plan.validation
        if args.json:
            _emit(
                {
                    "task_id": plan.task_id,
                    "plan_id": plan.plan_id,
                    "version": plan.version,
                    "hash": plan.hash,
                    "validation": validation.model_dump(mode="json")
                    if validation is not None
                    else None,
                }
            )
        elif validation is None:
            print(f"{plan.plan_id}: no lint result recorded")
        else:
            print(f"{plan.plan_id}: {'ok' if validation.ok else 'failed'}")
            for error in validation.errors:
                print(f"  error: {error}")
            for warning in validation.warnings:
                print(f"  warning: {warning}")
        return 0 if validation is not None and validation.ok else EXIT_POLICY

    if action == "eval":
        from works.application.planning.eval import evaluate

        payload = evaluate(paths, args.task_id)
        if args.json:
            _emit(payload)
        else:
            print(
                f"{payload['tasks']} task(s), {payload['plans']} plan(s), "
                f"{payload['validated']} validated, {payload['approved']} approved"
            )
            for mode, values in sorted(payload["by_mode"].items()):
                print(
                    f"  {mode:12} plans {values['plans']:3} ? validated {values['validated']:3} ? "
                    f"approved {values['approved']:3} ? proved {values['proved']:3}"
                )
            if payload["avg_critic_score"] is not None:
                print(f"  avg critic score: {payload['avg_critic_score']:.2f}")
            print(
                f"  planner cost: {payload['planner_tokens']} tokens / "
                f"${payload['planner_usd']:.4f}"
            )
        return 0

    if action == "diff":
        before = store.load(
            args.task_id, getattr(args, "from_version", None) or store.versions(args.task_id)[0]
        )
        after = store.load(
            args.task_id,
            getattr(args, "to_version", None) or store.versions(args.task_id)[-1],
        )
        before_steps = {step.id: step for step in before.steps}
        after_steps = {step.id: step for step in after.steps}
        added = sorted(set(after_steps) - set(before_steps))
        removed = sorted(set(before_steps) - set(after_steps))
        changed = sorted(
            step_id
            for step_id in set(before_steps) & set(after_steps)
            if before_steps[step_id].model_dump() != after_steps[step_id].model_dump()
        )
        payload = {
            "task_id": args.task_id,
            "from": before.plan_id,
            "to": after.plan_id,
            "added": added,
            "removed": removed,
            "changed": changed,
        }
        if args.json:
            _emit(payload)
        else:
            print(f"{before.plan_id} -> {after.plan_id}")
            print(f"  added:   {', '.join(added) or 'none'}")
            print(f"  removed: {', '.join(removed) or 'none'}")
            print(f"  changed: {', '.join(changed) or 'none'}")
        return 0

    if action not in ("replan",) and not args.scenarios:
        raise ConfigError("`works plan` needs --scenarios PATH")
    from works.adapters.processes.runner import SubprocessRunner
    from works.adapters.queue.ledger import Ledger
    from works.adapters.queue.store import Queue
    from works.application.settings import BuilderSettings, load_builder_settings, settings_path
    from works.application.supervisor import Supervisor

    queue = Queue(paths)
    settings = load_builder_settings(paths) if settings_path(paths).exists() else BuilderSettings()
    task = queue.load(args.task_id)
    mode, planner, critic = _planner_for(
        paths, settings, args, task.flow, mode=getattr(args, "mode", None)
    )
    supervisor = Supervisor(
        paths=paths,
        queue=queue,
        ledger=Ledger(paths.ledger),
        harness=None,
        runner=SubprocessRunner(),
        planner_mode=mode,
        planner=planner,
        critic=critic,
    )
    import asyncio

    plan = asyncio.run(supervisor.draft_task_plan(args.task_id, scenario_set=Path(args.scenarios)))
    if args.json:
        _emit(plan.model_dump(mode="json"))
    else:
        print(plan_markdown(plan))
        print(f"plan file: {store.directory(plan.task_id) / f'v{plan.version}.json'}")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    if args.gate == "release":
        from works.application.delivery.release import approve_release, release_packet

        packet = release_packet(_paths(args), args.task_id, require_release_gate=False)
        if not packet.ready:
            if args.json:
                _emit(
                    {
                        "ok": False,
                        "task_id": args.task_id,
                        "ready": False,
                        "blockers": packet.blockers,
                    }
                )
            else:
                print(f"release blocked: {args.task_id}")
                for blocker in packet.blockers:
                    print(f"  blocker: {blocker}")
            return EXIT_BLOCKED
        task, packet, created = approve_release(_paths(args), args.task_id)
        body = {
            "ok": True,
            "created": created,
            "task": task.model_dump(mode="json"),
            "release": packet.as_dict(),
        }
        if args.json:
            _emit(body)
        elif created:
            print(
                f"release approved: {args.task_id} is now {task.state.value} "
                f"at {packet.commit} (gate 2; nothing is published)"
            )
        else:
            print(f"already released: {args.task_id} at {packet.commit}")
        return 0
    if args.gate != "plan":
        raise ConfigError(f"unknown gate {args.gate!r}; expected plan or release")
    from works.application.approvals.gates import approve_plan

    updated, _ = approve_plan(
        _paths(args),
        args.task_id,
        by="cli",
        plan_id=getattr(args, "plan", None),
        plan_hash=getattr(args, "plan_hash", None),
    )
    if args.json:
        _emit({"task": updated.model_dump(mode="json")})
    else:
        print(f"plan approved: {args.task_id} is now {updated.state.value}")
    return 0
