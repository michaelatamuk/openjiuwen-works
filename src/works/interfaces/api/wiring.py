"""Shared application state for the local API daemon."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from works.adapters.queue.ledger import Ledger
from works.adapters.queue.store import Queue
from works.application.settings import BuilderSettings, load_builder_settings, settings_path
from works.config.paths import WorksPaths, load_paths
from works.domain.errors import ConfigError
from works.interfaces.api.jobs import JobRunner
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
    write_lock: threading.Lock = field(default_factory=threading.Lock)


def build_state(
    paths: WorksPaths | Path | None = None,
    *,
    writable: bool = False,
    bootstrap_token: str | None = None,
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
    )
