"""Wire a supervisor from the saved settings and the command-line flags."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from works.domain.errors import ConfigError
from works.interfaces.cli.commands.common import _paths, _queue

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
