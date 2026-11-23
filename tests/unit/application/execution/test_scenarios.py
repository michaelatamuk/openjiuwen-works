from __future__ import annotations

from pathlib import Path

import pytest

from works.application.execution.scenarios import judge, load_scenario_set
from works.domain.errors import ConfigError
from works.domain.records import Priority, ScenarioOutcome


def outcome(
    scenario_id: str, priority: Priority, passed: bool, weight: float = 1.0
) -> ScenarioOutcome:
    return ScenarioOutcome(
        id=scenario_id,
        priority=priority,
        weight=weight,
        passed=passed,
        exit_code=0 if passed else 1,
        duration_ms=10,
        output_sha256="0" * 64,
    )


def test_loads_the_fixture_set(scenario_set: Path) -> None:
    loaded = load_scenario_set(scenario_set)
    assert loaded.p0_ids == ["add-positive", "add-negative"]
    assert loaded.p1_ids == ["mul-positive"]
    assert loaded.scenarios[0].argv("python", scenario_set.parent)[0] == "python"


def test_all_p0_pass_allows() -> None:
    verdict = judge(
        [
            outcome("a", Priority.P0, True),
            outcome("b", Priority.P1, True),
        ],
        run_id="r-1",
    )
    assert verdict.allow
    assert verdict.p1_pass_rate == 1.0


def test_a_failed_p0_blocks_even_if_p1_passes() -> None:
    verdict = judge(
        [outcome("a", Priority.P0, False), outcome("b", Priority.P1, True)],
        run_id="r-1",
    )
    assert not verdict.allow
    assert verdict.p0_failed == ["a"]


def test_p1_below_eighty_percent_blocks() -> None:
    verdict = judge(
        [
            outcome("a", Priority.P0, True),
            outcome("b", Priority.P1, True),
            outcome("c", Priority.P1, False),
        ],
        run_id="r-1",
    )
    assert not verdict.allow
    assert verdict.p1_pass_rate == 0.5


def test_p1_weights_are_respected() -> None:
    verdict = judge(
        [
            outcome("a", Priority.P0, True),
            outcome("b", Priority.P1, True, weight=4.0),
            outcome("c", Priority.P1, False, weight=1.0),
        ],
        run_id="r-1",
    )
    assert verdict.allow
    assert verdict.p1_pass_rate == 0.8


def test_p0_only_never_fails_on_p1() -> None:
    verdict = judge([outcome("a", Priority.P0, True)], run_id="r-1")
    assert verdict.allow
    assert verdict.p1_pass_rate == 1.0


def test_outcomes_are_sorted_for_stable_evidence() -> None:
    verdict = judge(
        [outcome("z", Priority.P0, True), outcome("a", Priority.P1, True)],
        run_id="r-1",
    )
    assert [item.id for item in verdict.outcomes] == ["a", "z"]


def test_a_set_without_p0_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "set.yaml"
    path.write_text(
        "schema_version: 1\nscenarios:\n  - id: a\n    priority: P1\n    script: a.py\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(ConfigError):
        load_scenario_set(path)


def test_a_missing_script_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "set.yaml"
    path.write_text(
        "schema_version: 1\nscenarios:\n  - id: a\n    priority: P0\n    script: absent.py\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(ConfigError):
        load_scenario_set(path)


def test_duplicate_ids_are_refused(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("pass\n", encoding="utf-8", newline="\n")
    path = tmp_path / "set.yaml"
    path.write_text(
        "schema_version: 1\nscenarios:\n"
        "  - id: a\n    priority: P0\n    script: a.py\n"
        "  - id: a\n    priority: P1\n    script: a.py\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(ConfigError):
        load_scenario_set(path)
