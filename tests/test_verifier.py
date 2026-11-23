from __future__ import annotations

from pathlib import Path

import pytest

from works.adapters.processes.runner import CommandResult
from works.application.execution.verifier import (
    DockerVerifier,
    LocalVerifier,
    Mount,
    verifier_from_name,
)
from works.domain.errors import ConfigError


class RecordingRunner:
    def __init__(self, *, exit_code: int = 0, stdout: str = "") -> None:
        self.calls: list[tuple[list[str], Path, dict[str, str] | None, int]] = []
        self._exit_code = exit_code
        self._stdout = stdout

    def run(self, argv, cwd, *, env=None, timeout_s=600):
        self.calls.append((list(argv), cwd, env, timeout_s))
        return CommandResult(
            argv=tuple(argv),
            cwd=str(cwd),
            exit_code=self._exit_code,
            duration_ms=1,
            stdout=self._stdout,
            stderr="",
        )


def test_local_verifier_delegates_to_the_runner(tmp_path: Path) -> None:
    runner = RecordingRunner()
    verifier = LocalVerifier(runner)

    result = verifier.run(["python", "-m", "pytest"], tmp_path, timeout_s=30)

    assert result.ok
    assert runner.calls == [(["python", "-m", "pytest"], tmp_path, None, 30)]


def test_docker_verifier_isolates_the_container(tmp_path: Path) -> None:
    worktree = tmp_path / "worktrees" / "t-1"
    scenarios = tmp_path / "scenarios"
    worktree.mkdir(parents=True)
    scenarios.mkdir()
    runner = RecordingRunner()
    verifier = DockerVerifier(
        runner=runner,
        image="works-verifier:1",
        mounts=(
            Mount(tmp_path / "worktrees", "/works/worktrees", read_only=False),
            Mount(scenarios, "/works/scenarios"),
        ),
    )

    verifier.run(
        ["python", f"{worktree}/test.py", f"{scenarios}/case.py"],
        worktree,
        env={"PYTHONPATH": str(worktree)},
        timeout_s=45,
    )

    argv, cwd, env, timeout_s = runner.calls[0]
    assert argv[:2] == ["docker", "run"]
    assert "--network=none" in argv
    assert "--cap-drop=ALL" in argv
    assert "--security-opt=no-new-privileges" in argv
    assert "-w" in argv and argv[argv.index("-w") + 1] == "/works/worktrees/t-1"
    assert f"{tmp_path / 'worktrees'}:/works/worktrees" in argv[argv.index("-v") + 1]
    assert f"{scenarios}:/works/scenarios:ro" in argv
    assert "PYTHONPATH=/works/worktrees/t-1" in argv
    assert argv[-1] == "/works/scenarios/case.py"
    assert cwd == worktree
    assert env is None
    assert timeout_s == 105


def test_a_worktree_outside_every_mount_is_refused(tmp_path: Path) -> None:
    verifier = DockerVerifier(runner=RecordingRunner(), mounts=(Mount(tmp_path / "a", "/a"),))

    with pytest.raises(ConfigError, match="outside every verifier mount"):
        verifier.docker_argv(["pytest"], tmp_path / "b")


def test_a_container_without_mounts_is_refused() -> None:
    with pytest.raises(ConfigError, match="at least one mount"):
        DockerVerifier(runner=RecordingRunner()).docker_argv(["pytest"], Path.cwd())


def test_docker_availability_checks_the_daemon(tmp_path: Path) -> None:
    verifier = DockerVerifier(
        runner=RecordingRunner(exit_code=1),
        mounts=(Mount(tmp_path, "/works"),),
    )

    assert verifier.available() is False


def test_docker_availability_accepts_a_reachable_daemon(tmp_path: Path) -> None:
    verifier = DockerVerifier(
        runner=RecordingRunner(stdout="27.3.1"),
        mounts=(Mount(tmp_path, "/works"),),
    )

    assert verifier.available() is True


def test_the_local_verifier_is_the_default() -> None:
    verifier = verifier_from_name("local", RecordingRunner())

    assert isinstance(verifier, LocalVerifier)
    assert verifier.name == "local"


def test_unknown_verifier_names_are_refused() -> None:
    with pytest.raises(ConfigError, match="unknown verifier"):
        verifier_from_name("podman", RecordingRunner())


def test_the_docker_image_can_come_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKS_VERIFIER_IMAGE", "registry/verifier:9")

    verifier = verifier_from_name("docker", RecordingRunner())

    assert isinstance(verifier, DockerVerifier)
    assert verifier.image == "registry/verifier:9"
