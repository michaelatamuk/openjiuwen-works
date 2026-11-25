from __future__ import annotations

from pathlib import Path

import pytest

from works.application.reproduce import detect
from works.domain.errors import ConfigError


def test_manifest_detection_covers_five_ecosystems(tmp_path: Path) -> None:
    cases = {
        "pyproject.toml": "pytest",
        "package.json": "npm",
        "go.mod": "go",
        "Cargo.toml": "cargo",
        "pom.xml": "mvn",
    }
    for marker, expected in cases.items():
        repo = tmp_path / marker.replace(".", "-")
        repo.mkdir()
        (repo / marker).write_text("", encoding="utf-8")
        found = detect.from_repo(repo)
        assert found is not None
        assert expected in found.command
        assert found.source == "detected"


def test_the_repo_override_wins(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    override = tmp_path / ".works" / "reproduce.yaml"
    override.parent.mkdir()
    override.write_text(
        "command: ['python', '-m', 'pytest', 'tests/test_core.py', '-q']\n", "utf-8"
    )

    found = detect.choose(tmp_path, "FAILED tests/other.py::test_other")

    assert found is not None
    assert found.source == "repo-config"
    assert found.command[-2] == "tests/test_core.py"


def test_an_invalid_override_is_a_config_error(tmp_path: Path) -> None:
    override = tmp_path / ".works" / "reproduce.yaml"
    override.parent.mkdir()
    override.write_text("command: not-a-list\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="command must be"):
        detect.from_repo(tmp_path)


def test_a_failing_test_name_narrows_the_check() -> None:
    found = detect.from_signal("CI failed: FAILED tests/test_core.py::test_add - assert 1 == 2")

    assert found is not None
    assert found.source == "signal"
    assert "tests/test_core.py::test_add" in found.command


def test_free_text_does_not_invent_a_command() -> None:
    assert detect.from_signal("add subtracts instead of adding") is None


def test_a_quoted_command_is_taken_as_advice() -> None:
    found = detect.from_signal("reproduce with `pytest -q tests/test_core.py`")

    assert found is not None
    assert "pytest" in " ".join(found.command)
