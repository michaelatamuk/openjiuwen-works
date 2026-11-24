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
    def scenarios(self) -> Path:
        return self.root.parent / "works-scenarios"

    def ensure(self) -> WorksPaths:
        for directory in (self.queue, self.runs, self.worktrees, self.state):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    def task_dir(self, task_id: str) -> Path:
        return self.queue / task_id

    def run_dir(self, run_id: str) -> Path:
        return self.runs / run_id


def resolve_root(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    env = os.environ.get("WORKS_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def load_paths(explicit: Path | None = None) -> WorksPaths:
    return WorksPaths(resolve_root(explicit)).ensure()
