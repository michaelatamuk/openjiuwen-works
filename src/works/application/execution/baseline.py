"""Run the checks on the base commit, so a failure can be attributed.

Off by default: it doubles the check time. `WORKS_DIFFERENTIAL=1` turns it on.
"""

from __future__ import annotations

import os
from pathlib import Path

from works.adapters.git.repo import GitRepo
from works.adapters.processes.runner import CommandResult, SubprocessRunner
from works.domain.flow import Node


def enabled() -> bool:
    return os.environ.get("WORKS_DIFFERENTIAL", "").strip().lower() in {"1", "true", "yes", "on"}


def run(
    repo: GitRepo,
    base_commit: str,
    node: Node,
    worktrees: Path,
    run_id: str,
) -> CommandResult | None:
    target = worktrees / f"{run_id}-baseline" / "repo"
    if target.exists():
        repo.worktree_remove(target)
    repo.worktree_add(target, base_commit)
    try:
        return SubprocessRunner().run(node.argv(), target, timeout_s=min(node.timeout_s, 300))
    finally:
        repo.worktree_remove(target)


def _signature(result: CommandResult) -> str:
    lines = [line.strip() for line in result.output.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def same_failure(baseline: CommandResult | None, candidate: CommandResult | None) -> bool:
    """A failure that already existed at the base commit looks the same at the end."""
    if baseline is None or candidate is None:
        return False
    return (
        not baseline.ok
        and not candidate.ok
        and baseline.exit_code == candidate.exit_code
        and _signature(baseline) == _signature(candidate)
    )
