"""Thin, typed git operations. No shell, no string interpolation into a command line."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError, ConflictError, WorksError
from .runner import CommandResult, CommandRunner, SubprocessRunner


class GitError(WorksError):
    code = "git_error"
    exit_code = 6


@dataclass(frozen=True)
class DiffStat:
    path: str
    added: int
    removed: int


class GitRepo:
    def __init__(self, path: Path, runner: CommandRunner | None = None) -> None:
        self._path = path
        self._runner = runner or SubprocessRunner()

    @property
    def path(self) -> Path:
        return self._path

    def _git(self, *args: str, cwd: Path | None = None, timeout_s: int = 120) -> CommandResult:
        if shutil.which("git") is None:
            raise ConfigError("git is not installed or not on PATH")
        result = self._runner.run(
            ["git", "-C", str(cwd or self._path), *args], cwd or self._path, timeout_s=timeout_s
        )
        if not result.ok:
            raise GitError(f"git {' '.join(args)} failed: {result.output.strip()[:2000]}")
        return result

    def is_repo(self) -> bool:
        try:
            return bool(self._git("rev-parse", "--git-dir").stdout.strip())
        except (GitError, ConfigError):
            return False

    def head(self) -> str:
        return self._git("rev-parse", "HEAD").stdout.strip()

    def is_dirty(self) -> bool:
        return bool(self._git("status", "--porcelain").stdout.strip())

    def require_clean(self) -> None:
        if self.is_dirty():
            raise ConflictError(f"{self._path} has uncommitted changes; commit or stash first")

    def worktree_add(self, destination: Path, base: str) -> Path:
        if destination.exists():
            raise ConflictError(f"worktree path already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._git("worktree", "add", "--detach", str(destination), base)
        return destination

    def worktree_remove(self, destination: Path) -> None:
        if not destination.exists():
            return
        self._git("worktree", "remove", "--force", str(destination))

    def apply_patch(self, worktree: Path, patch: str, patch_path: Path | None = None) -> None:
        if not patch.strip():
            raise GitError("refusing to apply an empty patch")
        patch_file = patch_path or (worktree.parent / "proposal.diff")
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(patch, encoding="utf-8", newline="\n")
        self._git("apply", "--check", "--whitespace=nowarn", str(patch_file), cwd=worktree)
        self._git("apply", "--whitespace=nowarn", str(patch_file), cwd=worktree)

    def changed_files(self, worktree: Path) -> list[str]:
        output = self._git("diff", "--name-only", "HEAD", cwd=worktree).stdout
        return [line.strip() for line in output.splitlines() if line.strip()]

    def diff_text(self, worktree: Path) -> str:
        return self._git("diff", "HEAD", "--no-color", cwd=worktree).stdout

    def diff_stat(self, worktree: Path) -> list[DiffStat]:
        output = self._git("diff", "--numstat", "HEAD", cwd=worktree).stdout
        stats: list[DiffStat] = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            added_raw, removed_raw, path = parts
            stats.append(
                DiffStat(
                    path=path,
                    added=int(added_raw) if added_raw.isdigit() else -1,
                    removed=int(removed_raw) if removed_raw.isdigit() else -1,
                )
            )
        return stats


def init_repo(path: Path, *, message: str = "initial commit") -> GitRepo:
    """Create a committed git repository from a directory of files (tests and fixtures)."""
    if not path.exists():
        raise ConfigError(f"cannot initialise a missing directory: {path}")
    repo = GitRepo(path)
    if repo.is_repo():
        return repo
    runner = SubprocessRunner()
    for argv in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "core.autocrlf", "false"],
        ["git", "config", "core.eol", "lf"],
        ["git", "add", "-A"],
        [
            "git",
            "-c",
            "user.name=works",
            "-c",
            "user.email=works@local",
            "commit",
            "-q",
            "-m",
            message,
        ],
    ):
        result = runner.run(argv, path)
        if not result.ok:
            raise GitError(f"{' '.join(argv)} failed: {result.output.strip()[:2000]}")
    return repo
