from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.unit.application.delivery.test_release import _proved, _run
from works.adapters.queue.store import Queue
from works.application.team.launcher import run_team_verify
from works.domain.errors import ConfigError


def _fake_run(payload: dict, *, code: int = 0, stderr: str = ""):
    def run(argv, **kwargs):
        if code == 0:
            Path(argv[-1]).write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(argv, code, "", stderr)

    return run


def test_the_team_result_is_recorded_and_returned(paths, monkeypatch) -> None:
    task = _proved(paths)
    _run(paths, task)
    payload = {
        "verdict": "allow",
        "blockers": [],
        "inspector": {"role": "inspector", "allow": True, "checks": {"policy_ok": True}},
        "challenger": {"role": "challenger", "allow": True, "gaps": []},
    }
    monkeypatch.setattr("works.application.team.launcher.subprocess.run", _fake_run(payload))

    result = run_team_verify(
        paths, task.id, agent_python=Path(sys.executable), agent_core=Path(sys.executable).parent
    )

    assert result["verdict"] == "allow"
    events = [event for event in Queue(paths).events(task.id) if event.type == "team.verified"]
    assert events[-1].data["verdict"] == "allow"
    assert events[-1].data["inspector"]["checks"]["policy_ok"] is True


def test_a_failed_team_process_is_a_configuration_error(paths, monkeypatch) -> None:
    task = _proved(paths)
    _run(paths, task)
    monkeypatch.setattr(
        "works.application.team.launcher.subprocess.run",
        _fake_run({}, code=1, stderr="ModuleNotFoundError: agent_gateway"),
    )

    with pytest.raises(ConfigError, match="agent-core team failed"):
        run_team_verify(
            paths,
            task.id,
            agent_python=Path(sys.executable),
            agent_core=Path(sys.executable).parent,
        )


def test_a_missing_run_is_refused(paths) -> None:
    task = _proved(paths)

    with pytest.raises(ConfigError, match="no finished run"):
        run_team_verify(
            paths,
            task.id,
            agent_python=Path(sys.executable),
            agent_core=Path(sys.executable).parent,
        )


def test_a_missing_interpreter_is_refused(paths) -> None:
    task = _proved(paths)
    _run(paths, task)

    with pytest.raises(ConfigError, match="agent-core Python not found"):
        run_team_verify(paths, task.id, agent_python=Path("missing-python.exe"))
