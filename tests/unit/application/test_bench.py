from __future__ import annotations

import json
from pathlib import Path

import pytest

from works.application.bench import load_cases, run_bench
from works.domain.errors import WorksError


def _dataset(tmp_path: Path, cases: list[dict[str, object]]) -> Path:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        "\n".join(json.dumps(item) for item in cases) + "\n",
        encoding="utf-8",
    )
    return path


def _case(repo, factory_root, *, case_id: str, trace: str, **overrides) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": case_id,
        "repo": str(repo.path),
        "scenario_set": str(factory_root / "fixtures" / "scenarios" / "fix-add.yaml"),
        "trace": str(factory_root / "fixtures" / "traces" / trace),
        "expect_state": "proved",
        "expect_verdict": True,
    }
    payload.update(overrides)
    return payload


def test_a_good_case_and_a_hostile_case_are_both_scored(tmp_path: Path, repo, factory_root) -> None:
    cases = [
        _case(repo, factory_root, case_id="good", trace="fix-add.json"),
        _case(
            repo,
            factory_root,
            case_id="hostile",
            trace="hostile-sneaky.json",
            expect_state="blocked",
            expect_verdict=False,
        ),
    ]

    result = run_bench(load_cases(_dataset(tmp_path, cases)), workdir=tmp_path)

    assert result.cases == 2
    assert result.resolved == 2
    assert result.rate == 1.0
    assert all(item.ok for item in result.results)
    assert result.bound >= 1


def test_an_unexpected_state_is_not_resolved(tmp_path: Path, repo, factory_root) -> None:
    cases = [
        _case(repo, factory_root, case_id="wrong", trace="fix-add.json", expect_state="released")
    ]

    result = run_bench(load_cases(_dataset(tmp_path, cases)), workdir=tmp_path)

    assert result.cases == 1
    assert result.resolved == 0
    assert result.results[0].state == "proved"


def test_a_missing_repository_is_reported_not_raised(tmp_path: Path, factory_root) -> None:
    cases = [
        {
            "id": "gone",
            "repo": str(tmp_path / "missing"),
            "scenario_set": str(factory_root / "fixtures" / "scenarios" / "fix-add.yaml"),
            "trace": str(factory_root / "fixtures" / "traces" / "fix-add.json"),
        }
    ]

    result = run_bench(load_cases(_dataset(tmp_path, cases)), workdir=tmp_path)

    assert result.resolved == 0
    assert "repository not found" in result.results[0].error


def test_relative_paths_resolve_against_the_dataset(tmp_path: Path, repo, factory_root) -> None:
    target = factory_root / "fixtures" / "traces" / "fix-add.json"
    link = tmp_path / "trace.json"
    link.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    scenario = factory_root / "fixtures" / "scenarios" / "fix-add.yaml"
    (tmp_path / "scenario.yaml").write_text(scenario.read_text(encoding="utf-8"), encoding="utf-8")
    dataset = _dataset(
        tmp_path,
        [
            {
                "id": "rel",
                "repo": str(repo.path),
                "scenario_set": "scenario.yaml",
                "trace": "trace.json",
            }
        ],
    )

    cases = load_cases(dataset)

    assert cases[0].trace == link
    assert cases[0].scenario_set == tmp_path / "scenario.yaml"


def test_a_malformed_dataset_names_the_line(tmp_path: Path) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text('{"id": "x"}\n', encoding="utf-8")

    with pytest.raises(WorksError, match="line 1 is missing repo, scenario_set, trace"):
        load_cases(path)


def test_the_cli_accepts_an_empty_dataset(tmp_path: Path, paths) -> None:
    from tests.unit.interfaces.cli.test_cli import invoke, payload

    dataset = tmp_path / "empty.jsonl"
    dataset.write_text("", encoding="utf-8")

    result = invoke(paths, "bench", "--dataset", str(dataset), "--json")

    assert result.exit_code == 0, result.stderr
    body = payload(result)
    assert body["cases"] == 0
    assert body["resolved"] == 0
