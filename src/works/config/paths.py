"""Where things live. One root, resolved once, overridable for tests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorksPaths:
    root: Path

    @property
    def queue(self) -> Path:
        return self.root / "queue"

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def flows(self) -> Path:
        return self.root / "flows"

    @property
    def worktrees(self) -> Path:
        return self.root / "worktrees"

    @property
    def ledger(self) -> Path:
        return self.root / "ledger.jsonl"

    @property
    def state(self) -> Path:
        return self.root / ".works" / "state"

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def scenarios(self) -> Path:
        return self.root.parent / "works-scenarios"

    def ensure(self) -> WorksPaths:
        for directory in (self.queue, self.runs, self.worktrees, self.state):
            directory.mkdir(parents=True, exist_ok=True)
        if not self.flows.exists():
            from works.config.resources import copy_default_flows

            copy_default_flows(self.flows)
        return self

    def task_dir(self, task_id: str) -> Path:
        return self.queue / task_id

    def run_dir(self, run_id: str) -> Path:
        return self.runs / run_id


def resolve_root(explicit: Path | None = None) -> Path:
    """One home for every invocation, independent of the current directory.

    `--home` is the explicit override (tests and isolated demos), `WORKS_HOME` the environment
    override, and everything else lands in `~/.works` — so `works` run from any folder opens the
    same queue at the same URL.
    """
    if explicit is not None:
        return explicit.expanduser().resolve()
    env = os.environ.get("WORKS_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / ".works").expanduser().resolve()


def load_paths(explicit: Path | None = None) -> WorksPaths:
    return WorksPaths(resolve_root(explicit)).ensure()
