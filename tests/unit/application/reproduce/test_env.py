from __future__ import annotations

from pathlib import Path

from works.application.reproduce import env
from works.application.reproduce.classify import is_setup_failure


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, argv, cwd, *, env=None, timeout_s=600):
        from works.adapters.processes.runner import CommandResult

        self.calls.append(list(argv))
        return CommandResult(
            argv=tuple(argv), cwd=str(cwd), exit_code=0, duration_ms=1, stdout="", stderr=""
        )


def test_python_plan_creates_a_venv_and_installs(tmp_path: Path, paths) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("pytest\n", encoding="utf-8")

    planned = env.plan(paths, repo)

    assert planned.kind == "python"
    assert planned.fingerprint["python"]
    assert "requirements.txt" in planned.fingerprint


def test_node_plan_prefers_ci_with_a_lockfile(tmp_path: Path, paths) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text("{}", encoding="utf-8")
    (repo / "package-lock.json").write_text("{}", encoding="utf-8")

    planned = env.plan(paths, repo)

    assert planned.kind == "node"
    assert planned.commands == [["npm", "ci", "--silent"]]


def test_prepare_runs_every_planned_step(tmp_path: Path, paths) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    recorder = _Recorder()

    planned = env.prepare(paths, repo, runner=recorder)

    assert recorder.calls
    assert planned.kind == "python"


def test_a_missing_dependency_is_a_setup_failure() -> None:
    assert is_setup_failure("ModuleNotFoundError: No module named 'fastapi'")
    assert is_setup_failure("'pytest' is not recognized as an internal or external command")
    assert not is_setup_failure("assert add(2, 3) == 5")
