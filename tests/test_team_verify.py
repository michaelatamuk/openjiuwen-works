from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

AGENT_PYTHON = Path(
    os.environ.get("WORKS_AGENT_PYTHON")
    or r"C:\Workspace\openjiuwen\agent-core\.venv\Scripts\python.exe"
)
AGENT_CORE = Path(os.environ.get("WORKS_AGENT_CORE") or r"C:\Workspace\openjiuwen\agent-core")
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not AGENT_PYTHON.exists(), reason="agent-core checkout is not available")
def test_agent_core_team_returns_a_deterministic_verdict(tmp_path) -> None:
    result_path = tmp_path / "result.json"
    payload = {
        "policy_ok": True,
        "verdict_allow": True,
        "challenge_allow": True,
        "proof_sha256": "a" * 64,
        "commit": "abc1234",
        "risk": "low",
        "not_tested": [],
    }
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(AGENT_CORE), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    completed = subprocess.run(
        [str(AGENT_PYTHON), str(ROOT / "scripts" / "team_verify_worker.py"), str(result_path)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["verdict"] == "allow"
    assert result["inspector"]["checks"]["proof_bound"] is True
    assert result["challenger"]["allow"] is True
