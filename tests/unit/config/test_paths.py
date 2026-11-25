from __future__ import annotations

from pathlib import Path

import pytest

from works.config import paths


def test_the_default_home_is_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKS_HOME", raising=False)

    assert paths.resolve_root() == (Path.home() / ".works").resolve()


def test_the_environment_overrides_the_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("WORKS_HOME", str(tmp_path / "home"))

    assert paths.resolve_root() == (tmp_path / "home").resolve()


def test_an_explicit_home_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WORKS_HOME", str(tmp_path / "env-home"))

    assert paths.resolve_root(tmp_path / "explicit") == (tmp_path / "explicit").resolve()
