from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from works.errors import ConfigError, HarnessError
from works.harness.base import Proposal, ProposalRequest
from works.harness.swarm import (
    SwarmHarness,
    default_entrypoint,
    preflight,
)
from works.runner import CommandResult


def result(argv, cwd, *, exit_code=0, stdout="", stderr=""):
    return CommandResult(
        argv=tuple(argv),
        cwd=str(cwd),
        exit_code=exit_code,
        duration_ms=1,
        stdout=stdout,
        stderr=stderr,
    )


class SwarmRunner:
    def __init__(self, *, payload: Any = None, write_result: bool = True) -> None:
        self.calls: list[list[str]] = []
        self.payload = payload if payload is not None else {}
        self.write_result = write_result

    def run(self, argv, cwd, *, env=None, timeout_s=600):
        self.calls.append(list(argv))
        if "--works-result" in argv and self.write_result:
            target = Path(argv[argv.index("--works-result") + 1])
            target.write_text(json.dumps(self.payload), encoding="utf-8")
        return result(argv, cwd)


def harness(tmp_path: Path, runner: SwarmRunner) -> SwarmHarness:
    interpreter = tmp_path / "python.exe"
    interpreter.write_text("", encoding="utf-8")
    home = tmp_path / "jiuwenswarm"
    home.mkdir()
    return SwarmHarness(
        python=interpreter,
        home=home,
        entrypoint=["-m", "jiuwenswarm.channels.cli"],
        runner=runner,  # type: ignore[arg-type]
    )


def request(tmp_path: Path) -> ProposalRequest:
    return ProposalRequest(
        task_id="t-1",
        source_ref="FIRE-7",
        title="crash on start",
        worktree=tmp_path,
        base_commit="abc1234",
    )


def test_preflight_reports_a_missing_interpreter(tmp_path: Path) -> None:
    diagnostic = preflight(
        tmp_path / "absent.exe",
        home=tmp_path,
        runner=SwarmRunner(),  # type: ignore[arg-type]
    )

    assert diagnostic.ok is False
    assert "interpreter not found" in diagnostic.detail


def test_preflight_explains_the_missing_agent_gateway(tmp_path: Path) -> None:
    class BrokenRunner(SwarmRunner):
        def run(self, argv, cwd, *, env=None, timeout_s=600):
            return result(
                argv,
                cwd,
                exit_code=1,
                stderr="ModuleNotFoundError: No module named 'agent_gateway'",
            )

    home = tmp_path / "home"
    home.mkdir()
    diagnostic = preflight(
        Path(sys.executable),
        home=home,
        entrypoint=["-m", "jiuwenswarm.channels.cli"],
        runner=BrokenRunner(),  # type: ignore[arg-type]
    )

    assert diagnostic.ok is False
    assert "agent_gateway" in diagnostic.detail
    assert "WORKS_SWARM_ENTRYPOINT" in diagnostic.detail


def test_propose_reads_the_contract_result(tmp_path: Path) -> None:
    runner = SwarmRunner(
        payload={
            "patch": "diff --git a/x b/x\n",
            "touched_paths": ["x"],
            "model": "swarm-1",
            "tokens": 12,
        }
    )
    proposal = asyncio.run(harness(tmp_path, runner).propose(request(tmp_path)))

    assert isinstance(proposal, Proposal)
    assert proposal.patch.startswith("diff --git")
    assert proposal.touched_paths == ["x"]
    assert proposal.tokens == 12
    assert "--works-kind" in runner.calls[-1]
    assert runner.calls[-1][runner.calls[-1].index("--works-kind") + 1] == "propose"


def test_propose_fails_when_the_entrypoint_writes_nothing(tmp_path: Path) -> None:
    runner = SwarmRunner(write_result=False)

    with pytest.raises(HarnessError, match="produced no result"):
        asyncio.run(harness(tmp_path, runner).propose(request(tmp_path)))


def test_propose_rejects_invalid_json(tmp_path: Path) -> None:
    class BadJsonRunner(SwarmRunner):
        def run(self, argv, cwd, *, env=None, timeout_s=600):
            if "--works-result" in argv:
                Path(argv[argv.index("--works-result") + 1]).write_text("{", encoding="utf-8")
            return result(argv, cwd)

    with pytest.raises(HarnessError, match="invalid JSON"):
        asyncio.run(harness(tmp_path, BadJsonRunner()).propose(request(tmp_path)))


def test_challenge_reads_the_same_contract(tmp_path: Path) -> None:
    runner = SwarmRunner(payload={"allow": False, "reason": "no test", "concerns": ["coverage"]})
    challenge = asyncio.run(harness(tmp_path, runner).challenge(request(tmp_path), Proposal()))

    assert challenge.allow is False
    assert challenge.reason == "no test"
    assert challenge.concerns == ["coverage"]


def test_a_broken_platform_is_never_replaced_by_a_fake_build(tmp_path: Path) -> None:
    class BrokenRunner(SwarmRunner):
        def run(self, argv, cwd, *, env=None, timeout_s=600):
            return result(argv, cwd, exit_code=1, stderr="ModuleNotFoundError: agent_gateway")

    with pytest.raises(HarnessError, match="JiuwenSwarm is not ready"):
        asyncio.run(harness(tmp_path, BrokenRunner()).propose(request(tmp_path)))


def test_propose_rejects_a_non_object_result(tmp_path: Path) -> None:
    runner = SwarmRunner(payload=[])

    with pytest.raises(HarnessError, match="non-object"):
        asyncio.run(harness(tmp_path, runner).propose(request(tmp_path)))


def test_challenge_rejects_an_invalid_result(tmp_path: Path) -> None:
    runner = SwarmRunner(payload={"reason": "missing allow"})

    with pytest.raises(HarnessError, match="challenge is invalid"):
        asyncio.run(harness(tmp_path, runner).challenge(request(tmp_path), Proposal()))


def test_a_custom_entrypoint_is_probed_on_the_first_run(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    class Runner(SwarmRunner):
        def run(self, argv, cwd, *, env=None, timeout_s=600):
            self.calls.append(list(argv))
            return result(argv, cwd)

    runner = Runner()
    diagnostic = preflight(
        Path(sys.executable),
        home=home,
        entrypoint=["adapter"],
        runner=runner,  # type: ignore[arg-type]
    )

    assert diagnostic.ok is True
    assert "probed on the first real run" in diagnostic.detail
    assert runner.calls == []


def test_default_locations_can_come_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from works.harness.swarm import default_swarm_home, default_swarm_python

    monkeypatch.setenv("WORKS_SWARM_PYTHON", str(tmp_path / "py.exe"))
    monkeypatch.setenv("WORKS_SWARM_HOME", str(tmp_path / "swarm"))

    assert default_swarm_python() == tmp_path / "py.exe"
    assert default_swarm_home() == tmp_path / "swarm"


def test_the_entrypoint_comes_from_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKS_SWARM_ENTRYPOINT", '["adapter.py", "--flag"]')

    assert default_entrypoint() == ["adapter.py", "--flag"]

    monkeypatch.setenv("WORKS_SWARM_ENTRYPOINT", "not json")
    with pytest.raises(ConfigError, match="JSON array"):
        default_entrypoint()
