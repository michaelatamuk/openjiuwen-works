"""Shared application state for the local API daemon."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from works.adapters.queue.ledger import Ledger
from works.adapters.queue.store import Queue
from works.application.settings import BuilderSettings, load_builder_settings, settings_path
from works.config.paths import WorksPaths, load_paths
from works.domain.errors import ConfigError


@dataclass(frozen=True)
class AppState:
    paths: WorksPaths
    queue: Queue
    ledger: Ledger
    writable: bool
    settings: BuilderSettings | None


def build_state(paths: WorksPaths | Path | None = None, *, writable: bool = False) -> AppState:
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
    return AppState(
        paths=resolved,
        queue=Queue(resolved),
        ledger=Ledger(resolved.ledger),
        writable=writable,
        settings=settings,
    )
