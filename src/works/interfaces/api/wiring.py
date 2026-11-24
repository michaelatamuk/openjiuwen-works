"""Shared application state for the local API daemon."""

from __future__ import annotations

import argparse
import threading
from dataclasses import dataclass, field
from pathlib import Path

from works.adapters.queue.ledger import Ledger
from works.adapters.queue.store import Queue
from works.application.settings import BuilderSettings, load_builder_settings, settings_path
from works.application.supervisor import Supervisor
from works.config.paths import WorksPaths, load_paths
from works.domain.errors import ConfigError
from works.interfaces.api.jobs import JobRunner
from works.interfaces.api.live import EventHub
from works.interfaces.api.security import Security


@dataclass(frozen=True)
class AppState:
    paths: WorksPaths
    queue: Queue
    ledger: Ledger
    writable: bool
    settings: BuilderSettings | None
    security: Security
    jobs: JobRunner
    live: EventHub
    open_lan: bool = False
    write_lock: threading.Lock = field(default_factory=threading.Lock)
    stop_event: threading.Event = field(default_factory=threading.Event)


def build_state(
    paths: WorksPaths | Path | None = None,
    *,
    writable: bool = False,
    bootstrap_token: str | None = None,
    open_lan: bool = False,
) -> AppState:
    if isinstance(paths, WorksPaths):
        resolved = paths.ensure()
    elif paths is not None:
        resolved = WorksPaths(paths).ensure()
    else:
        resolved = load_paths().ensure()
    try:
        settings = load_builder_settings(resolved) if settings_path(resolved).exists() else None
    except ConfigError:
        settings = None
    queue = Queue(resolved)
    return AppState(
        paths=resolved,
        queue=queue,
        ledger=Ledger(resolved.ledger),
        writable=writable,
        settings=settings,
        security=Security(resolved, bootstrap_token=bootstrap_token),
        jobs=JobRunner(resolved, queue),
        live=EventHub(resolved),
        open_lan=open_lan,
    )


def build_supervisor(
    paths: WorksPaths,
    *,
    task_id: str | None = None,
    trace: str | None = None,
    live: bool = False,
    swarm: bool = False,
    model: str | None = None,
    model_base: str | None = None,
    prompt: str | None = None,
    ppma: str | None = None,
    ppma_space: str = "me",
    decision: str | None = None,
    verifier: str = "local",
    verifier_image: str | None = None,
) -> Supervisor:
    """Build a supervisor from saved settings, with optional per-run overrides."""
    from works.interfaces.cli.commands.wiring import _supervisor

    args = argparse.Namespace(
        home=paths.root,
        trace=Path(trace).expanduser().resolve() if trace else None,
        live=live,
        swarm=swarm,
        swarm_python=None,
        swarm_home=None,
        model=model,
        model_base=model_base,
        prompt=Path(prompt).expanduser().resolve() if prompt else None,
        ppma=ppma,
        ppma_space=ppma_space,
        decision=decision,
        verifier=verifier,
        verifier_image=verifier_image,
        task_id=task_id,
    )
    supervisor: Supervisor = _supervisor(args)
    return supervisor
