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
    EXIT_OK,
    EXIT_POLICY,
    EXIT_STATE,
    ConfigError,
    PolicyError,
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
            ensure_ascii=True,
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
    from .products import resolve_repo
    from .records import Source, SourceKind, TaskKind

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
    if args.gate == "release":
        from .release import approve_release, release_packet

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
    from .approvals import approve_plan

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


def cmd_team_verify(args: argparse.Namespace) -> int:
    from .team_task import run_team_verify

    result = run_team_verify(_paths(args), args.task_id)
    if args.json:
        _emit(result)
    else:
        print(f"team verdict: {result.get('verdict')}")
        for blocker in result.get("blockers") or []:
            print(f"  blocker: {blocker}")
    return 0 if result.get("verdict") == "allow" else EXIT_BLOCKED


def cmd_source_github(args: argparse.Namespace) -> int:
    from .products import resolve_repo
    from .sources import github_issues, ingest_issues

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
    from .products import resolve_repo
    from .sources import ingest_issues, jira_issues

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


def cmd_deliver(args: argparse.Namespace) -> int:
    from .deliver import deliver

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
    from .deploy import deploy

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
    from .confirm import confirm
    from .preview import PreviewScript

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


def cmd_source_detector(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .detectors import (
        fetch_alerts,
        ingest_alerts,
        ingest_named,
        read_alert_file,
    )
    from .products import resolve_repo

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
    from .harness.swarm import preflight

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


def cmd_plan(args: argparse.Namespace) -> int:
    from .planner import PlanStore, plan_markdown

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
        from .plan_eval import evaluate

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
    from .ledger import Ledger
    from .queue import Queue
    from .runner import SubprocessRunner
    from .settings import BuilderSettings, load_builder_settings, settings_path
    from .supervisor import Supervisor

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


def cmd_release(args: argparse.Namespace) -> int:
    from .release import release_packet

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
    from .harness.openjiuwen import default_base, default_cli, default_key, default_model
    from .harness.planner import HarnessCritic, HarnessPlanner

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
    from .harness.base import Harness
    from .harness.fake import FakeHarness
    from .ledger import Ledger
    from .runner import SubprocessRunner
    from .supervisor import Supervisor

    paths = _paths(args)
    from .settings import load_builder_settings, settings_path

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
        from .harness.swarm import SwarmHarness

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
        from .harness.openjiuwen import LiveHarness

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
        from .memory import PpmaMemory

        memory = PpmaMemory(ppma_url, space=args.ppma_space)
    from .verifier import DockerVerifier, Mount, verifier_from_name

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

    if args.trace is None and not args.live and not getattr(args, "swarm", False):
        raise ConfigError(
            "no builder configured: pass --trace PATH for a recorded run, "
            "--live for the OpenJiuwen harness, or --swarm for JiuwenSwarm; "
            "or save a builder in Settings"
        )

    task = _queue(args).load(args.task_id)
    repository = Path(task.repo)
    if args.live:
        from .readiness import assess

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


def cmd_wait(args: argparse.Namespace) -> int:
    from datetime import datetime

    from .records import TaskState

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


def cmd_dispatch(args: argparse.Namespace) -> int:
    import asyncio
    import time

    from .records import TaskState

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


def cmd_finding_add(args: argparse.Namespace) -> int:
    from .records import Finding

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
    from .records import Finding

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


def cmd_metrics(args: argparse.Namespace) -> int:
    from .escapes import read_report
    from .ledger import Ledger
    from .metrics import collect

    metrics = collect(
        _queue(args),
        Ledger(_paths(args).ledger),
        escape_report=read_report(_paths(args)),
    )
    if args.json:
        _emit({"metrics": metrics.model_dump(mode="json")})
        return 0
    print(
        table(
            ("metric", "value"),
            [
                ("tasks", metrics.tasks),
                ("proved", metrics.proved),
                ("blocked", metrics.blocked),
                ("human touches", metrics.human_touches),
                ("runs without human", metrics.runs_without_human),
                ("waiting (ms)", metrics.waiting_ms),
                ("median duration (ms)", metrics.median_duration_ms or "-"),
                ("tokens", metrics.tokens),
                ("usd", f"{metrics.usd:.4f}"),
                ("escapes", metrics.escapes),
                ("rework", metrics.rework),
            ],
        )
    )
    if metrics.per_task:
        print()
        print(
            table(
                ("task", "state", "ms", "touches", "waiting ms", "tokens", "usd"),
                [
                    (
                        item.task_id,
                        item.state.value,
                        item.duration_ms,
                        item.human_touches,
                        item.waiting_ms,
                        item.tokens,
                        f"{item.usd:.4f}",
                    )
                    for item in metrics.per_task
                ],
            )
        )
    return 0


def cmd_escapes(args: argparse.Namespace) -> int:
    from .escapes import append_events, scan, write_report

    report = scan(_paths(args), days=args.days)
    if not args.dry_run:
        write_report(_paths(args), report)
        append_events(_paths(args), report)
    if args.json:
        _emit(
            {
                "escapes": report.as_dict(),
                "written": not args.dry_run,
            }
        )
        return 0
    print(
        table(
            ("metric", "value"),
            [
                ("window (days)", report.window_days),
                ("escapes", report.escapes),
                ("rework", len(report.rework)),
            ],
        )
    )
    for finding in report.findings:
        print(f"  {finding.kind.value}: {finding.task_id} at {finding.evidence_commit[:12]}")
    for rework in report.rework:
        print(f"  rework: {rework.task_id} repeats {rework.previous_task_id}")
    return 0


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


def cmd_risk(args: argparse.Namespace) -> int:
    from .risk import RiskRating

    events = _queue(args).events(args.task_id)
    ratings = [
        RiskRating.model_validate(event.data) for event in events if event.type == "risk.rated"
    ]
    if not ratings:
        raise ConfigError(f"task {args.task_id} has no risk rating yet")
    latest = ratings[-1]
    if args.json:
        _emit({"risk": latest.model_dump(mode="json")})
        return 0
    print(f"{latest.level.value}: {latest.files} file(s), {latest.lines} line(s)")
    for reason in latest.reasons:
        print(f"- {reason}")
    if latest.owners:
        print(f"owners: {', '.join(latest.owners)}")
    print(
        f"reviewers: {latest.required_reviewers}"
        + (" (deeper verification)" if latest.deeper_verification else "")
    )
    return 0


def cmd_gate_list(args: argparse.Namespace) -> int:
    events = _queue(args).events(args.task_id)
    decisions = [
        {"seq": event.seq, "type": event.type, **event.data}
        for event in events
        if event.type in ("decision.made", "decision.shadow", "would_block")
    ]
    if args.json:
        _emit({"task_id": args.task_id, "events": decisions})
        return 0
    print(
        table(
            ("seq", "type", "gate", "detail"),
            [
                (
                    item["seq"],
                    item["type"],
                    item.get("gate", "-"),
                    item.get("action") or item.get("reason") or item.get("agree") or "-",
                )
                for item in decisions
            ],
        )
    )
    return 0


def cmd_gate_report(args: argparse.Namespace) -> int:
    queue = _queue(args)
    task_ids = [args.task_id] if args.task_id else [task.id for task in queue.list_tasks()]
    report: list[dict[str, Any]] = []
    for task_id in task_ids:
        decisions = [
            event
            for event in queue.events(task_id)
            if event.type in ("decision.made", "decision.shadow", "would_block")
        ]
        by_gate: dict[str, dict[str, int]] = {}
        for event in decisions:
            gate = str(event.data.get("gate", "unknown"))
            bucket = by_gate.setdefault(gate, {"decisions": 0, "would_block": 0, "disagree": 0})
            if event.type == "decision.made":
                bucket["decisions"] += 1
            elif event.type == "would_block":
                bucket["would_block"] += 1
            elif event.data.get("agree") is False:
                bucket["disagree"] += 1
        report.append({"task_id": task_id, "gates": by_gate})
    if args.json:
        _emit({"report": report})
        return 0
    rows = [
        (
            item["task_id"],
            gate,
            counts["decisions"],
            counts["would_block"],
            counts["disagree"],
        )
        for item in report
        for gate, counts in sorted(item["gates"].items())
    ]
    print(table(("task", "gate", "decisions", "would_block", "disagree"), rows))
    return 0


def cmd_flake_add(args: argparse.Namespace) -> int:
    from .flakes import add_flake

    flake = add_flake(
        _paths(args),
        task_id=args.task_id,
        scenario_id=args.scenario,
        owner=args.owner,
        reason=args.reason,
        days=args.days,
    )
    if args.json:
        _emit({"flake": flake.model_dump(mode="json")})
    else:
        print(f"flake recorded: {flake.id} ({flake.scenario_id}, owner {flake.owner})")
    return 0


def cmd_flake_list(args: argparse.Namespace) -> int:
    from .flakes import active_flakes, load_flakes

    flakes = active_flakes(_paths(args)) if args.active else load_flakes(_paths(args))
    if args.json:
        _emit({"flakes": [flake.model_dump(mode="json") for flake in flakes]})
        return 0
    print(
        table(
            ("id", "task", "scenario", "owner", "expires", "status"),
            [
                (
                    flake.id,
                    flake.task_id,
                    flake.scenario_id,
                    flake.owner,
                    flake.expires_at.isoformat(timespec="seconds") if flake.expires_at else "-",
                    flake.status.value,
                )
                for flake in flakes
            ],
        )
    )
    return 0


def cmd_decision_replay(args: argparse.Namespace) -> int:
    from .decision import build_decision_port
    from .decision_eval import load_cases, replay, summary

    cases = load_cases(Path(args.cases))
    candidate = build_decision_port(args.provider)
    outcomes = replay(cases, candidate)
    payload = summary(outcomes)
    if args.json:
        _emit(payload)
    else:
        print(
            table(
                ("case", "deterministic", "candidate", "agree", "unsafe"),
                [
                    (
                        item.case_id,
                        item.deterministic.action,
                        item.candidate.action,
                        "yes" if item.agree else "no",
                        "YES" if item.unsafe_allow else "no",
                    )
                    for item in outcomes
                ],
            )
        )
        print(
            f"{payload['cases']} cases · {payload['agree']} agree · "
            f"{payload['disagree']} differ · {payload['unsafe_allow']} unsafe allow"
        )
    return EXIT_POLICY if payload["unsafe_allow"] else 0


def cmd_ui(args: argparse.Namespace) -> int:
    import webbrowser

    from .ui.server import serve

    if args.write and args.read_only:
        raise ConfigError("use either --write or --read-only, not both")
    server = serve(_paths(args), host=args.host, port=args.port, write=args.write)
    address = server.server_address
    host = str(address[0])
    port = int(address[1])
    url = f"http://{host}:{port}/"
    mode = "read-write" if args.write else "read-only"
    if args.json:
        _emit({"url": url, "readonly": not args.write, "write": bool(args.write)})
    else:
        print(f"openJiuwen Works {mode} preview: {url}")
        print("Press Ctrl+C to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


def cmd_memory_backfill(args: argparse.Namespace) -> int:
    from datetime import UTC, datetime

    from .memory import NullMemory, PpmaMemory
    from .memory_ops import backfill_runs

    url = args.ppma or os.environ.get("WORKS_PPMA_URL")
    if not url and not args.dry_run:
        raise ConfigError("PPMA url is required; pass --ppma or set WORKS_PPMA_URL")
    since = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ConfigError(f"invalid --since value {args.since!r}") from exc
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)
    memory = NullMemory() if args.dry_run else PpmaMemory(url or "", space=args.space)
    entries = backfill_runs(
        _paths(args),
        memory,
        limit=args.limit,
        dry_run=args.dry_run,
        task_id=args.task,
        since=since,
    )
    counts = {
        status: sum(1 for entry in entries if entry.status == status)
        for status in ("reported", "skipped", "failed")
    }
    payload = {
        "url": url,
        "dry_run": args.dry_run,
        "reported": counts["reported"],
        "skipped": counts["skipped"],
        "failed": counts["failed"],
        "runs": [entry.as_dict() for entry in entries],
    }
    if args.json:
        print(
            json.dumps(
                {"ok": counts["failed"] == 0, **payload},
                ensure_ascii=False,
                default=str,
                separators=(",", ":"),
            )
        )
    elif args.dry_run:
        print(f"PPMA backfill dry run: {len(entries)} readable run(s); nothing was sent.")
    else:
        print(
            f"PPMA backfill: {counts['reported']} reported, "
            f"{counts['skipped']} skipped, {counts['failed']} failed."
        )
        for entry in entries:
            if entry.status == "failed":
                print(f"  {entry.run_id}: {entry.error}", file=sys.stderr)
    return EXIT_INTERNAL if counts["failed"] else 0


def cmd_readiness(args: argparse.Namespace) -> int:
    from .readiness import assess

    repo = Path(args.repo or ".").expanduser()
    report = assess(repo, run_commands=not args.no_run, timeout_s=args.timeout)
    if args.json:
        payload = {"ok": report.status != "fail", **report.as_dict()}
        print(json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":")))
    else:
        print(f"Readiness: {report.status.upper()} ({report.passed}/{report.total})")
        for check in report.checks:
            mark = "✓" if check.status == "pass" else "!" if check.status == "fail" else "-"
            detail = f" - {check.detail}" if check.detail else ""
            print(f"  {mark} {check.label}{detail}")
        if report.unknown_suppressions:
            print("  Unknown suppressions:")
            for item in report.unknown_suppressions[:20]:
                print(f"    {item.location}  {item.text}")
        print(f"  {report.note}")
    return EXIT_BLOCKED if report.status == "fail" else 0


def cmd_memory_recall(args: argparse.Namespace) -> int:
    from .memory import PpmaMemory

    url = args.ppma or os.environ.get("WORKS_PPMA_URL")
    if not url:
        raise ConfigError("PPMA url is required; pass --ppma or set WORKS_PPMA_URL")
    memory = PpmaMemory(url, space=args.space)
    try:
        statements = memory.recall(view=args.view, limit=args.limit)
    except RuntimeError as exc:
        raise ConfigError(str(exc)) from exc
    if args.json:
        _emit({"view": args.view, "statements": statements})
    elif not statements:
        print("No memory statements.")
    else:
        for statement in statements:
            print(f"- {statement}")
    return 0


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
    submit.add_argument(
        "--task-kind",
        default="fix",
        choices=("fix", "check-change"),
        help="fix or check-change",
    )
    submit.add_argument("--json", action="store_true")
    submit.set_defaults(func=cmd_submit)

    source = sub.add_parser("source", help="Read a tracker and queue its open issues")
    source_sub = source.add_subparsers(dest="source_command", required=True)
    source_github = source_sub.add_parser("github", help="GitHub Issues intake")
    source_github.add_argument("repository", help="owner/name")
    source_github.add_argument("--product", required=True)
    source_github.add_argument("--repo", type=Path, default=None)
    source_github.add_argument("--label", default=None)
    source_github.add_argument("--limit", type=int, default=20)
    source_github.add_argument("--json", action="store_true")
    source_github.set_defaults(func=cmd_source_github)
    source_jira = source_sub.add_parser("jira", help="Jira JQL intake")
    source_jira.add_argument("--url", required=True, help="Jira base URL")
    source_jira.add_argument("--jql", required=True)
    source_jira.add_argument("--product", required=True)
    source_jira.add_argument("--repo", type=Path, default=None)
    source_jira.add_argument("--limit", type=int, default=20)
    source_jira.add_argument("--json", action="store_true")
    source_jira.set_defaults(func=cmd_source_jira)
    source_detector = source_sub.add_parser("detector", help="Firing alerts into the queue")
    detector_target = source_detector.add_mutually_exclusive_group(required=True)
    detector_target.add_argument("--name", default=None, help="Configured detector name")
    detector_target.add_argument("--file", default=None, help="JSON or NDJSON alert file")
    detector_target.add_argument("--url", default=None, help="Alertmanager-style endpoint")
    source_detector.add_argument("--product", default=None)
    source_detector.add_argument("--repo", type=Path, default=None)
    source_detector.add_argument("--limit", type=int, default=50)
    source_detector.add_argument("--json", action="store_true")
    source_detector.set_defaults(func=cmd_source_detector)

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

    plan = sub.add_parser("plan", help="Draft, show, lint or diff versioned plans")
    plan.add_argument("task_id")
    plan.add_argument("--action", choices=("draft", "show", "lint", "diff"), default="draft")
    plan.add_argument("--scenarios", default=None)
    plan.add_argument("--version", type=int, default=None)
    plan.add_argument("--from", dest="from_version", type=int, default=None)
    plan.add_argument("--to", dest="to_version", type=int, default=None)
    plan.add_argument(
        "--mode",
        choices=("deterministic", "shadow", "assisted", "deep", "spec", "auto"),
        default=None,
    )
    plan.add_argument("--model", default=None)
    plan.add_argument("--model-base", default=None)
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(func=cmd_plan)

    approve = sub.add_parser("approve", help="Approve the plan gate")
    approve.add_argument("task_id")
    approve.add_argument("--gate", default="plan", help="plan or release")
    approve.add_argument("--plan", default=None, help="Plan id to approve (default: latest)")
    approve.add_argument("--plan-hash", default=None, help="Exact plan hash to approve")
    approve.add_argument("--json", action="store_true")
    approve.set_defaults(func=cmd_approve)

    release = sub.add_parser("release", help="Build the read-only release packet")
    release.add_argument("task_id")
    release.add_argument("--json", action="store_true")
    release.set_defaults(func=cmd_release)

    deliver = sub.add_parser("deliver", help="Push the released change and open a pull request")
    deliver.add_argument("task_id")
    deliver.add_argument("--remote", default="origin")
    deliver.add_argument("--base", default="main", help="Pull-request base branch")
    deliver.add_argument("--provider", choices=("none", "github", "gitlab"), default="none")
    deliver.add_argument("--tracker", choices=("none", "github", "gitlab", "jira"), default=None)
    deliver.add_argument("--dry-run", action="store_true")
    deliver.add_argument("--json", action="store_true")
    deliver.set_defaults(func=cmd_deliver)

    deploy = sub.add_parser("deploy", help="Run the owner-approved deploy command")
    deploy.add_argument("task_id")
    deploy.add_argument("--command", default=None, help="Deploy command or JSON argv array")
    deploy.add_argument("--environment", default="staging", help="Target environment name")
    deploy.add_argument("--dry-run", action="store_true")
    deploy.add_argument("--force", action="store_true", help="Repeat a recorded deploy")
    deploy.add_argument("--json", action="store_true")
    deploy.set_defaults(func=cmd_deploy)

    confirm = sub.add_parser("confirm", help="Re-check the released commit and close the loop")
    confirm.add_argument("task_id")
    target = confirm.add_mutually_exclusive_group()
    target.add_argument("--url", default=None, help="HTTP endpoint to check")
    target.add_argument("--command", default=None, help="Command to run in a fresh worktree")
    target.add_argument("--preview", default=None, help="Playwright preview script (YAML)")
    confirm.add_argument("--provider", choices=("none", "github", "gitlab", "jira"), default="none")
    confirm.add_argument("--tracker", choices=("none", "github", "gitlab", "jira"), default=None)
    confirm.add_argument("--close", action="store_true", help="Close the source issue on success")
    confirm.add_argument("--force", action="store_true")
    confirm.add_argument("--json", action="store_true")
    confirm.set_defaults(func=cmd_confirm)

    team = sub.add_parser("team", help="Run the agent-core verification team")
    team_sub = team.add_subparsers(dest="team_command", required=True)
    team_verify = team_sub.add_parser("verify", help="Inspector + challenger + reporter")
    team_verify.add_argument("task_id")
    team_verify.add_argument("--json", action="store_true")
    team_verify.set_defaults(func=cmd_team_verify)

    swarm = sub.add_parser("swarm", help="Check the JiuwenSwarm builder boundary")
    swarm_sub = swarm.add_subparsers(dest="swarm_command", required=True)
    swarm_doctor = swarm_sub.add_parser("doctor", help="Preflight the isolated builder")
    swarm_doctor.add_argument("--python", default=None)
    swarm_doctor.add_argument("--home", default=None)
    swarm_doctor.add_argument("--json", action="store_true")
    swarm_doctor.set_defaults(func=cmd_swarm_doctor)

    run = sub.add_parser("run", help="Reproduce, plan, build, check, prove")
    run.add_argument("task_id")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--approve-plan", action="store_true")
    run.add_argument("--scenarios", default=None)
    run.add_argument("--quarantine", default=None)
    run.add_argument("--trace", type=Path, default=None)
    run.add_argument("--live", action="store_true")
    run.add_argument("--swarm", action="store_true")
    run.add_argument("--swarm-python", default=None)
    run.add_argument("--swarm-home", default=None)
    run.add_argument("--model", default=None)
    run.add_argument("--model-base", default=None)
    run.add_argument("--prompt", type=Path, default=None)
    run.add_argument("--ppma", default=None)
    run.add_argument("--ppma-space", default="me")
    run.add_argument("--decision", choices=("off", "shadow", "laix"), default=None)
    run.add_argument("--verifier", choices=("local", "docker"), default="local")
    run.add_argument("--verifier-image", default=None)
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)

    wait = sub.add_parser("wait", help="Put a task into a waiting state")
    wait.add_argument("task_id")
    wait.add_argument("--on", choices=("review", "ci", "deploy"), required=True)
    wait.add_argument("--wake-on", required=True)
    wait.add_argument("--deadline", default=None)
    wait.add_argument("--next", default=None)
    wait.add_argument("--default", default=None)
    wait.add_argument("--json", action="store_true")
    wait.set_defaults(func=cmd_wait)

    wake = sub.add_parser("wake", help="Wake a waiting task on its event")
    wake.add_argument("task_id")
    wake.add_argument("--event", required=True)
    wake.add_argument("--json", action="store_true")
    wake.set_defaults(func=cmd_wake)

    dispatch = sub.add_parser("dispatch", help="Claim and run ready tasks")
    dispatch.add_argument("--limit", type=int, default=10)
    dispatch.add_argument("--watch", action="store_true")
    dispatch.add_argument("--interval", type=int, default=10)
    dispatch.add_argument("--approve-plan", action="store_true")
    dispatch.add_argument("--scenarios", default=None)
    dispatch.add_argument("--quarantine", default=None)
    dispatch.add_argument("--trace", type=Path, default=None)
    dispatch.add_argument("--live", action="store_true")
    dispatch.add_argument("--swarm", action="store_true")
    dispatch.add_argument("--swarm-python", default=None)
    dispatch.add_argument("--swarm-home", default=None)
    dispatch.add_argument("--model", default=None)
    dispatch.add_argument("--model-base", default=None)
    dispatch.add_argument("--prompt", type=Path, default=None)
    dispatch.add_argument("--ppma", default=None)
    dispatch.add_argument("--ppma-space", default="me")
    dispatch.add_argument("--decision", choices=("off", "shadow", "laix"), default=None)
    dispatch.add_argument("--verifier", choices=("local", "docker"), default="local")
    dispatch.add_argument("--verifier-image", default=None)
    dispatch.add_argument("--json", action="store_true")
    dispatch.set_defaults(func=cmd_dispatch)

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

    finding = sub.add_parser("finding", help="Structured findings for a task")
    finding_sub = finding.add_subparsers(dest="finding_command", required=True)
    finding_add = finding_sub.add_parser("add", help="Record a finding")
    finding_add.add_argument("task_id")
    finding_add.add_argument("--summary", required=True)
    finding_add.add_argument("--step", default="")
    finding_add.add_argument("--confidence", default=None)
    finding_add.add_argument("--uncertainty", default="")
    finding_add.add_argument("--evidence", action="append", default=[])
    finding_add.add_argument("--json", action="store_true")
    finding_add.set_defaults(func=cmd_finding_add)
    finding_list = finding_sub.add_parser("list", help="List findings")
    finding_list.add_argument("task_id")
    finding_list.add_argument("--json", action="store_true")
    finding_list.set_defaults(func=cmd_finding_list)

    metrics = sub.add_parser("metrics", help="Attention and cost metrics")
    metrics.add_argument("--json", action="store_true")
    metrics.set_defaults(func=cmd_metrics)

    escapes = sub.add_parser("escapes", help="Attribute reverts, hotfixes and repeated work")
    escapes.add_argument("--days", type=int, default=14)
    escapes.add_argument("--dry-run", action="store_true", help="Scan without writing the report")
    escapes.add_argument("--json", action="store_true")
    escapes.set_defaults(func=cmd_escapes)

    memory = sub.add_parser("memory", help="PPMA memory tools")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    backfill = memory_sub.add_parser("backfill", help="Report already-finished runs to PPMA")
    backfill.add_argument("--ppma", default=None, help="PPMA base URL")
    backfill.add_argument("--space", default="me")
    backfill.add_argument("--limit", type=int, default=None)
    backfill.add_argument("--task", default=None)
    backfill.add_argument("--since", default=None)
    backfill.add_argument("--dry-run", action="store_true")
    backfill.add_argument("--json", action="store_true")
    backfill.set_defaults(func=cmd_memory_backfill)
    recall = memory_sub.add_parser("recall", help="Read PPMA memory statements")
    recall.add_argument("--ppma", default=None, help="PPMA base URL")
    recall.add_argument("--space", default="me")
    recall.add_argument("--view", default="about_me")
    recall.add_argument("--limit", type=int, default=8)
    recall.add_argument("--json", action="store_true")
    recall.set_defaults(func=cmd_memory_recall)

    risk = sub.add_parser("risk", help="Show the latest risk rating")
    risk.add_argument("task_id")
    risk.add_argument("--json", action="store_true")
    risk.set_defaults(func=cmd_risk)

    gate = sub.add_parser("gate", help="Inspect gate decisions and observe-mode blocks")
    gate_sub = gate.add_subparsers(dest="gate_command", required=True)
    gate_list = gate_sub.add_parser("list", help="List decisions for a task")
    gate_list.add_argument("task_id")
    gate_list.add_argument("--json", action="store_true")
    gate_list.set_defaults(func=cmd_gate_list)
    gate_report = gate_sub.add_parser("report", help="Summarize decisions and observe blocks")
    gate_report.add_argument("task_id", nargs="?", default=None)
    gate_report.add_argument("--json", action="store_true")
    gate_report.set_defaults(func=cmd_gate_report)

    flake = sub.add_parser("flake", help="Flaky tests are defects with an owner and an expiry")
    flake_sub = flake.add_subparsers(dest="flake_command", required=True)
    flake_add = flake_sub.add_parser("add", help="Record a flake")
    flake_add.add_argument("task_id")
    flake_add.add_argument("--scenario", required=True)
    flake_add.add_argument("--owner", required=True)
    flake_add.add_argument("--reason", required=True)
    flake_add.add_argument("--days", type=int, default=14)
    flake_add.add_argument("--json", action="store_true")
    flake_add.set_defaults(func=cmd_flake_add)
    flake_list = flake_sub.add_parser("list", help="List flakes")
    flake_list.add_argument("--active", action="store_true")
    flake_list.add_argument("--json", action="store_true")
    flake_list.set_defaults(func=cmd_flake_list)

    decision = sub.add_parser("decision", help="Replay historical gate cases")
    decision_sub = decision.add_subparsers(dest="decision_command", required=True)
    decision_replay = decision_sub.add_parser(
        "replay", help="Compare a candidate policy with the rule"
    )
    decision_replay.add_argument("--cases", required=True)
    decision_replay.add_argument("--provider", choices=("off", "shadow", "laix"), default="laix")
    decision_replay.add_argument("--json", action="store_true")
    decision_replay.set_defaults(func=cmd_decision_replay)

    ui = sub.add_parser("ui", help="Open the read-only preview window")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--read-only", action="store_true", help="Only supported mode")
    ui.add_argument("--write", action="store_true", help="Not implemented")
    ui.add_argument("--no-open", action="store_true", help="Do not open a browser")
    ui.add_argument("--json", action="store_true")
    ui.set_defaults(func=cmd_ui)

    schema = sub.add_parser("schema", help="Print every persisted schema")
    schema.add_argument("--json", action="store_true")
    schema.set_defaults(func=cmd_schema)

    doctor = sub.add_parser("doctor", help="Check config, git, harness, container, credentials")
    doctor.add_argument("--repo", type=Path, default=None)
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    readiness = sub.add_parser(
        "readiness", help="Decide whether a repository is ready for autonomous work"
    )
    readiness.add_argument("--repo", type=Path, default=None)
    readiness.add_argument("--no-run", action="store_true", help="Static checks only")
    readiness.add_argument("--timeout", type=int, default=120)
    readiness.add_argument("--json", action="store_true")
    readiness.set_defaults(func=cmd_readiness)
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
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
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
