from __future__ import annotations

import json
from pathlib import Path

import pytest

from works.application.execution.quarantine import (
    QuarantineError,
    ensure_outside,
    is_inside,
    load,
    write,
)


def test_is_inside_handles_prefixes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert is_inside(repo / "a.py", repo)
    assert not is_inside(tmp_path / "repo-other" / "a.py", repo)


def test_a_quarantine_list_outside_the_repository_round_trips(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    path = tmp_path / "quarantine.json"
    write(path, repo, ["tests/", "conftest.py"])
    loaded = load(path, repo)
    assert loaded.paths == ["tests/", "conftest.py"]


def test_a_quarantine_list_inside_the_repository_is_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(QuarantineError):
        ensure_outside(repo / "quarantine.json", repo, label="quarantine list")


def test_invalid_json_is_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    path = tmp_path / "q.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(QuarantineError):
        load(path, repo)


def test_a_missing_list_is_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(QuarantineError):
        load(tmp_path / "absent.json", repo)


def test_the_written_file_is_json_with_a_schema_version(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    path = tmp_path / "q.json"
    write(path, repo, ["tests/"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["paths"] == ["tests/"]
