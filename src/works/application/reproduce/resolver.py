"""Managed checkouts: clone once, fetch, resolve the requested ref, reuse.

A task may name a remote and a ref instead of an already-cloned path. Clones live under
`<home>/repos/<slug>`; the worktree is still created from the resolved commit by the supervisor.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from works.adapters.git.repo import GitRepo
from works.adapters.processes.runner import CommandRunner, SubprocessRunner
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError

PR = re.compile(r"^(?:pull/|pr/|#)(?P<number>\d+)$")
SHA = re.compile(r"^[0-9a-f]{7,40}$")


@dataclass(frozen=True)
class Checkout:
    path: Path
    commit: str
    ref: str


def slug(url: str) -> str:
    match = re.search(r"[:/](?P<owner>[\w.-]+)/(?P<name>[\w.-]+?)(?:\.git)?/?$", url.strip())
    if match:
        raw = f"{match.group('owner')}-{match.group('name')}"
    else:
        raw = Path(url.rstrip("/")).name or "repo"
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip(".-")
    if cleaned:
        return cleaned[:80]
    return "repo-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]


def _git(runner: CommandRunner, args: list[str], cwd: Path) -> str:
    result = runner.run(["git", *args], cwd, timeout_s=600)
    if not result.ok:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise ConfigError(
            f"git {' '.join(args)} failed: {detail[-1] if detail else result.exit_code}"
        )
    return result.stdout.strip()


def _verify(runner: CommandRunner, repo: Path, ref: str) -> str | None:
    result = runner.run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], repo, timeout_s=60)
    return result.stdout.strip() if result.ok and result.stdout.strip() else None


def resolve(runner: CommandRunner, repo: Path, ref: str | None) -> str:
    if not ref:
        for candidate in ("HEAD", "refs/remotes/origin/HEAD"):
            commit = _verify(runner, repo, candidate)
            if commit:
                return commit
        raise ConfigError(f"{repo} has no HEAD to reproduce from")
    match = PR.match(ref.strip())
    if match:
        number = match.group("number")
        _git(
            runner,
            ["fetch", "origin", f"+refs/pull/{number}/head:refs/remotes/origin/pr/{number}"],
            repo,
        )
        commit = _verify(runner, repo, f"refs/remotes/origin/pr/{number}")
        if commit:
            return commit
        raise ConfigError(f"pull request {number} is not available on origin")
    for candidate in (ref, f"refs/tags/{ref}", f"refs/remotes/origin/{ref}"):
        commit = _verify(runner, repo, candidate)
        if commit:
            return commit
    raise ConfigError(f"ref {ref!r} was not found after fetch")


def checkout(
    paths: WorksPaths,
    url: str,
    ref: str | None,
    *,
    runner: CommandRunner | None = None,
    offline: bool = False,
) -> Checkout:
    command_runner = runner or SubprocessRunner()
    target = paths.root / "repos" / slug(url)
    fresh = not (target / ".git").is_dir()
    if fresh and offline:
        raise ConfigError(
            f"{url} is not cached under {target.parent}; offline mode cannot clone it"
        )
    if fresh:
        target.parent.mkdir(parents=True, exist_ok=True)
        _git(command_runner, ["clone", "--no-checkout", url, str(target)], target.parent)
    elif not offline:
        _git(command_runner, ["fetch", "--prune", "--tags", "origin"], target)
    commit = resolve(command_runner, target, ref)
    return Checkout(path=target, commit=commit, ref=ref or "")


def open_checkout(path: Path) -> GitRepo:
    repo = GitRepo(path)
    if not repo.is_repo():
        raise ConfigError(f"not a git repository: {path}")
    return repo
