from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import check_typing_ratchet as ratchet

OUTPUT = """
src/a.py:1: error: Explicit "Any" is not allowed  [explicit-any]
src/a.py:2: error: Returning Any from function declared to return "str"  [no-any-return]
src/b.py:1: error: unused "type: ignore" comment  [unused-ignore]
"""


def test_only_any_errors_are_counted() -> None:
    assert ratchet.parse(OUTPUT) == {"src/a.py": 2}


def test_new_any_in_a_file_is_a_regression() -> None:
    found = ratchet.regressions({"src/a.py": 3}, {"files": {"src/a.py": 2}})

    assert found and "src/a.py" in found[0]


def test_a_new_file_with_any_is_a_regression() -> None:
    found = ratchet.regressions({"src/new.py": 1}, {"files": {"src/a.py": 2}})

    assert any("src/new.py" in item for item in found)


def test_a_smaller_count_is_accepted() -> None:
    assert ratchet.regressions({"src/a.py": 1}, {"files": {"src/a.py": 2}}) == []


def test_update_records_the_current_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = tmp_path / "typing-baseline.json"
    monkeypatch.setattr(ratchet, "BASELINE", baseline)

    ratchet.write({"src/a.py": 2})
    payload = json.loads(baseline.read_text(encoding="utf-8"))

    assert payload["total"] == 2
    assert payload["files"] == {"src/a.py": 2}
    assert payload["flags"] == list(ratchet.FLAGS)
