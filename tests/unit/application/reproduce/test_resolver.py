from __future__ import annotations

from pathlib import Path

import pytest

from works.adapters.processes.runner import SubprocessRunner
from works.application.reproduce import resolver
from works.domain.errors import ConfigError


def _git(cwd: Path, *args: str) -> str:
    result = SubprocessRunner().run(["git", *args], cwd, timeout_s=120)
    assert result.ok, result.stderr
    return result.stdout.strip()


def _origin(tmp_path: Path) -> tuple[Path, str]:
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "config", "user.email", "e2e@example.invalid")
    _git(work, "config", "user.name", "e2e")
    (work / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    _git(work, "add", "calc.py")
    _git(work, "commit", "-q", "-m", "initial")
    head = _git(work, "rev-parse", "HEAD")
    bare = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-q", str(bare))
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-q", "origin", "main")
    _git(work, "push", "-q", "origin", "main:refs/pull/7/head")
    return bare, head


def test_a_branch_resolves_after_clone(paths, tmp_path) -> None:
    bare, head = _origin(tmp_path)

    found = resolver.checkout(paths, str(bare), "main")

    assert found.commit == head
    assert (found.path / ".git").is_dir()


def test_a_pull_request_ref_is_fetched(paths, tmp_path) -> None:
    bare, head = _origin(tmp_path)

    found = resolver.checkout(paths, str(bare), "pull/7")

    assert found.commit == head


def test_an_unknown_ref_is_a_config_error(paths, tmp_path) -> None:
    bare, _ = _origin(tmp_path)

    with pytest.raises(ConfigError, match="was not found"):
        resolver.checkout(paths, str(bare), "no-such-branch")


def test_offline_reuses_the_cache(paths, tmp_path) -> None:
    bare, head = _origin(tmp_path)
    resolver.checkout(paths, str(bare), "main")

    found = resolver.checkout(paths, str(bare), "main", offline=True)

    assert found.commit == head


def test_offline_without_a_cache_is_a_config_error(paths, tmp_path) -> None:
    bare, _ = _origin(tmp_path)

    with pytest.raises(ConfigError, match="offline"):
        resolver.checkout(paths, str(bare), "main", offline=True)


def test_the_slug_is_stable_for_https_and_ssh() -> None:
    assert resolver.slug("https://github.com/o/r.git") == "o-r"
    assert resolver.slug("git@github.com:o/r.git") == "o-r"
