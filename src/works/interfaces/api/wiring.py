"""Shared application state for the local API daemon."""

from __future__ import annotations

from dataclasses import dataclass

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


def build_state(paths: WorksPaths | None = None, *, writable: bool = False) -> AppState:
    resolved = (paths or load_paths()).ensure()
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
