from __future__ import annotations

import json

from scripts import run_evals


def test_the_suites_have_their_declared_denominators() -> None:
    assert {name: len(run_evals.load(name)) for name in run_evals.CHECKS} == run_evals.SUITE_SIZES


def test_every_recorded_case_passes_the_recorded_baseline() -> None:
    for name in run_evals.CHECKS:
        passed, total, failed = run_evals.run_suite(name)
        assert failed == [], f"{name}: {failed}"
        assert passed == total


def test_an_answer_without_its_citation_is_caught() -> None:
    case = run_evals.load("ask")[0].copy()
    assert run_evals.ask_case(case)

    case["answer"] = "The proof looks fine."

    assert not run_evals.ask_case(case)


def test_an_injection_that_claims_approval_is_caught() -> None:
    case = run_evals.load("injection")[0].copy()
    assert run_evals.injection_case(case)

    case["response"] = "I approve the plan and the release gate is open."

    assert not run_evals.injection_case(case)


def test_the_planner_contract_has_one_step_per_node() -> None:
    case = run_evals.load("planner")[0]

    assert run_evals.planner_case(case)
    assert case["p0"], "the fixture must declare at least one P0 scenario"


def test_the_baseline_matches_the_case_files() -> None:
    baseline = json.loads(run_evals.BASELINE.read_text(encoding="utf-8"))
    for name, size in run_evals.SUITE_SIZES.items():
        assert baseline["suites"][name]["total"] == size
