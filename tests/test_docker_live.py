"""A live container verifier test; CI provides Docker, local runs are opt-in."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from works.adapters.processes.runner import SubprocessRunner
from works.application.execution.verifier import DockerVerifier, Mount

pytestmark = pytest.mark.skipif(
    os.environ.get("WORKS_TEST_DOCKER") != "1",
    reason="set WORKS_TEST_DOCKER=1 with a running Docker daemon",
)


def test_the_container_verifier_runs_a_command_without_host_paths(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    verifier = DockerVerifier(
        runner=SubprocessRunner(),
        mounts=(
            Mount(worktree, "/works/repo", read_only=False),
            Mount(scenarios, "/works/scenarios"),
        ),
    )

    assert verifier.available() is True
    result = verifier.run(["python", "-c", "print('container-ok')"], worktree)

    assert result.ok is True
    assert "container-ok" in result.output
    assert verifier.isolation == "container"
