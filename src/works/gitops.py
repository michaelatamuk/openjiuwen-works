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

    def head(self, cwd: Path | None = None) -> str:
        return self._git("rev-parse", "HEAD", cwd=cwd).stdout.strip()

    def show(self, rev: str, path: str) -> str | None:
        """Read a file at a commit without touching the worktree; None when absent."""
        try:
            return self._git("show", f"{rev}:{path}", timeout_s=30).stdout
        except GitError:
            return None

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

    def untracked_files(self, worktree: Path) -> list[str]:
        output = self._git("ls-files", "--others", "--exclude-standard", cwd=worktree).stdout
        return [line.strip() for line in output.splitlines() if line.strip()]

    def all_changed_files(self, worktree: Path) -> list[str]:
        return sorted({*self.changed_files(worktree), *self.untracked_files(worktree)})

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

    def stage_all(self, *, cwd: Path | None = None) -> None:
        """Stage tracked changes and new files, but never runtime artifacts."""
        self._git("add", "-A", "--", ".", ":(exclude).works", cwd=cwd)

    def staged_files(self, *, cwd: Path | None = None) -> list[str]:
        output = self._git("diff", "--cached", "--name-only", cwd=cwd).stdout
        return [line.strip() for line in output.splitlines() if line.strip()]

    def commit_staged(
        self,
        message: str,
        *,
        cwd: Path | None = None,
        author: str = "openjiuwen-works",
        email: str = "works@local",
    ) -> str:
        self._git(
            "-c",
            f"user.name={author}",
            "-c",
            f"user.email={email}",
            "commit",
            "-q",
            "-m",
            message,
            cwd=cwd,
        )
        return self.head(cwd=cwd)

    def commit_all(
        self,
        message: str,
        *,
        cwd: Path | None = None,
        author: str = "openjiuwen-works",
        email: str = "works@local",
    ) -> str:
        """Stage the change and commit it, leaving runtime artifacts out of the tree."""
        self.stage_all(cwd=cwd)
        if not self.staged_files(cwd=cwd):
            return self.head(cwd=cwd)
        return self.commit_staged(message, cwd=cwd, author=author, email=email)

    def remote_url(self, remote: str = "origin") -> str:
        return self._git("remote", "get-url", remote).stdout.strip()

    def has_remote(self, remote: str = "origin") -> bool:
        try:
            self._git("remote", "get-url", remote, timeout_s=30)
        except GitError:
            return False
        return True

    def set_branch(self, name: str, commit: str) -> None:
        self._git("branch", "-f", name, commit)

    def branch_commit(self, name: str) -> str | None:
        try:
            return self._git("rev-parse", "--verify", f"refs/heads/{name}").stdout.strip() or None
        except GitError:
            return None

    def remote_commit(self, remote: str, branch: str) -> str | None:
        output = self._git("ls-remote", remote, f"refs/heads/{branch}", timeout_s=60).stdout.strip()
        return output.split()[0] if output else None

    def push(self, remote: str, branch: str, *, cwd: Path | None = None) -> CommandResult:
        return self._git(
            "push",
            "--porcelain",
            remote,
            f"refs/heads/{branch}:refs/heads/{branch}",
            cwd=cwd,
            timeout_s=300,
        )


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
