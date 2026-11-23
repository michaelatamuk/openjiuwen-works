"""Run the agent-core verification team without importing agent-core into Works.

The team itself lives in `works.team_verify` and runs in agent-core's interpreter. This module
prepares the payload, starts that subprocess and records the result. The CLI and the GUI share it.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import tempfile
from pathlib import Path
from typing import Any

from works.adapters.queue.store import Queue
from works.application.delivery.release import latest_run_dir
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError
from works.domain.evidence import Evidence
from works.domain.records import RunRecord


def default_agent_python() -> Path:
    return Path(
        os.environ.get("WORKS_AGENT_PYTHON")
        or r"C:\Workspace\openjiuwen\agent-core\.venv\Scripts\python.exe"
    )


def run_team_verify(
    paths: WorksPaths,
    task_id: str,
    *,
    agent_python: Path | None = None,
    agent_core: Path | None = None,
    timeout_s: int = 120,
) -> dict[str, Any]:
    queue = Queue(paths)
    task = queue.load(task_id)
    run_dir = latest_run_dir(paths, task_id)
    if run_dir is None:
        raise ConfigError(f"task {task.id} has no finished run")
    evidence = Evidence.model_validate_json((run_dir / "evidence.json").read_text(encoding="utf-8"))
    record = RunRecord.model_validate_json((run_dir / "run.json").read_text(encoding="utf-8"))
    interpreter = agent_python or default_agent_python()
    if not interpreter.exists():
        raise ConfigError("agent-core Python not found; set WORKS_AGENT_PYTHON to its interpreter")
    payload = {
        "task_id": task.id,
        "run_id": record.run_id,
        "gate": "release",
        "policy_ok": bool(evidence.policy.ok),
        "verdict_allow": bool(evidence.verdict and evidence.verdict.allow),
        "challenge_allow": evidence.challenge.allow if evidence.challenge else None,
        "proof_sha256": evidence.proof_sha256,
        "commit": record.base_commit,
        "risk": evidence.risk.level.value if evidence.risk else "low",
        "not_tested": evidence.not_tested,
    }
    repo_root = Path(__file__).resolve().parents[4]
    core = agent_core or Path(
        os.environ.get("WORKS_AGENT_CORE") or r"C:\Workspace\openjiuwen\agent-core"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(repo_root / "src"), str(core), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    handle, tmp_name = tempfile.mkstemp(prefix="works-team-", suffix=".json")
    os.close(handle)
    result_path = Path(tmp_name)
    try:
        completed = subprocess.run(  # nosec B603
            [
                str(interpreter),
                str(repo_root / "scripts" / "team_verify_worker.py"),
                str(result_path),
            ],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env=env,
            timeout=timeout_s,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip().splitlines()
            raise ConfigError(
                f"agent-core team failed: {detail[-1] if detail else completed.returncode}"
            )
        raw = json.loads(result_path.read_text(encoding="utf-8"))
    finally:
        result_path.unlink(missing_ok=True)
    if not isinstance(raw, dict):
        raise ConfigError("agent-core team returned a non-object result")
    queue.append(
        task.id,
        "team.verified",
        {
            "verdict": raw.get("verdict"),
            "blockers": raw.get("blockers") or [],
            "team": "inspector+challenger+reporter",
            "inspector": raw.get("inspector"),
            "challenger": raw.get("challenger"),
        },
    )
    return raw
