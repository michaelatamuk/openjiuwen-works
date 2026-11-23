from __future__ import annotations

from pathlib import Path

from works.application.doctor import failed, run_checks
from works.config import WorksPaths


def test_required_checks_pass(paths: WorksPaths, repo) -> None:
    results = run_checks(paths, repo=repo.path)
    required = [result for result in results if result.required]
    assert required
    assert all(result.status == "ok" for result in required)
    assert not failed(results)


def test_a_quarantine_file_inside_the_repository_fails(paths: WorksPaths, repo) -> None:
    (repo.path / "quarantine.json").write_text("{}", encoding="utf-8")
    results = run_checks(paths, repo=repo.path)
    quarantine = next(result for result in results if result.name == "quarantine")
    assert quarantine.status == "fail"
    assert not failed(results), "quarantine is a warning, not a required failure"


def test_scenarios_inside_the_repository_fail(paths: WorksPaths, tmp_path: Path) -> None:
    (tmp_path / "works-scenarios").mkdir()
    results = run_checks(paths, repo=tmp_path)
    scenarios = next(result for result in results if result.name == "scenarios")
    assert scenarios.status == "fail"


def test_missing_credentials_are_a_warning(paths: WorksPaths, repo, monkeypatch) -> None:
    monkeypatch.delenv("WORKS_BUILDER_API_KEY", raising=False)
    monkeypatch.delenv("WORKS_VERIFIER_API_KEY", raising=False)
    results = run_checks(paths, repo=repo.path, environ={"PATH": "/bin"})
    credentials = next(result for result in results if result.name == "credentials")
    assert credentials.status == "warn"


def test_the_same_key_for_builder_and_verifier_is_not_a_split(paths: WorksPaths, repo) -> None:
    results = run_checks(
        paths,
        repo=repo.path,
        environ={"WORKS_MODEL_KEY": "same", "WORKS_VERIFIER_API_KEY": "same"},
    )
    credentials = next(result for result in results if result.name == "credentials")
    assert credentials.status == "warn"
    assert "same key" in credentials.detail


def test_separate_builder_and_verifier_keys_are_ok(paths: WorksPaths, repo) -> None:
    results = run_checks(
        paths,
        repo=repo.path,
        environ={"WORKS_MODEL_KEY": "builder", "WORKS_VERIFIER_API_KEY": "verifier"},
    )
    credentials = next(result for result in results if result.name == "credentials")
    assert credentials.status == "ok"


def test_a_failed_required_check_fails_the_command(paths: WorksPaths) -> None:
    results = run_checks(paths, repo=paths.root)
    result = results[0]
    broken = result.model_copy(update={"status": "fail", "required": True})
    assert failed([broken])
