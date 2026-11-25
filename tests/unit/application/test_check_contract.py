from __future__ import annotations

from pathlib import Path

from tests.unit.domain.test_evidence import fixed_evidence
from works.adapters.processes.runner import CommandResult
from works.application.execution import baseline
from works.application.planning.checks import scenario_digest
from works.application.supervisor import review
from works.domain.evidence import render_markdown


def _result(exit_code: int, text: str, cwd: str = "/repo") -> CommandResult:
    return CommandResult(
        argv=("pytest",),
        cwd=cwd,
        exit_code=exit_code,
        duration_ms=10,
        stdout=text,
        stderr="",
    )


def test_the_scenario_digest_changes_when_a_script_changes(tmp_path: Path) -> None:
    from works.application.execution.scenarios import Scenario, ScenarioSet
    from works.domain.records import Priority

    (tmp_path / "a.py").write_text("print(1)\n", encoding="utf-8")
    scenarios = ScenarioSet(scenarios=[Scenario(id="a", priority=Priority.P0, script="a.py")])
    first = scenario_digest(tmp_path, scenarios)

    (tmp_path / "a.py").write_text("print(2)\n", encoding="utf-8")

    assert scenario_digest(tmp_path, scenarios) != first


def test_a_pre_existing_failure_is_recognised() -> None:
    base = _result(1, "assert add(1, 2) == 3\nE assert -1 == 3")
    same = _result(1, "assert add(1, 2) == 3\nE assert -1 == 3", cwd="/worktree")
    other = _result(1, "TypeError: unsupported operand")

    assert baseline.same_failure(base, same) is True
    assert baseline.same_failure(base, other) is False
    assert baseline.same_failure(base, _result(0, "passed")) is False


def test_review_independence_is_only_required_for_high_risk(monkeypatch) -> None:
    monkeypatch.setenv("WORKS_REQUIRE_SPLIT_REVIEW", "1")

    assert review.independent("low", provider_split=False, credential_split=False) is True
    assert review.independent("high", provider_split=False, credential_split=False) is False
    assert review.independent("high", provider_split=True, credential_split=False) is True
    assert review.independent("high", provider_split=False, credential_split=True) is True

    monkeypatch.delenv("WORKS_REQUIRE_SPLIT_REVIEW")
    assert review.independent("high", provider_split=False, credential_split=False) is True


def test_the_page_shows_the_base_commit_check() -> None:
    evidence = fixed_evidence().model_copy(
        update={"baseline_exit": 1, "baseline_output_sha256": "b" * 64}
    )

    page = render_markdown(evidence)

    assert "base commit check" in page
    assert "b" * 64 in page
