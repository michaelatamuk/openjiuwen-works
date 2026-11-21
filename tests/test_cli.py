from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

from works.cli import main
from works.gitops import GitRepo
from works.queue import Queue
from works.records import TaskState
from works.risk import RiskLevel, RiskRating


@dataclass(frozen=True)
class Result:
    exit_code: int
    stdout: str
    stderr: str


def invoke(paths, *args: str) -> Result:
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--home", str(paths.root), *args])
    except SystemExit as exc:
        code = int(exc.code) if exc.code is not None else 0
    return Result(code, out.getvalue(), err.getvalue())


def payload(result: Result) -> dict:
    return json.loads(result.stdout.strip().splitlines()[-1])


def submit_cli(paths, repo) -> dict:
    result = invoke(paths, "submit", "--ref", "GH-1", "--repo", str(repo.path), "--json")
    assert result.exit_code == 0, result.stdout + result.stderr
    return payload(result)


def test_help_works(paths) -> None:
    result = invoke(paths, "--help")
    assert result.exit_code == 0
    assert "software factory" in result.stdout.lower()


def test_submit_is_idempotent_from_the_cli(paths, repo) -> None:
    first = invoke(
        paths,
        "submit",
        "--ref",
        "GH-1",
        "--title",
        "bug",
        "--repo",
        str(repo.path),
        "--json",
    )
    assert first.exit_code == 0, first.stdout
    first_payload = payload(first)
    assert first_payload["created"] is True
    second = invoke(paths, "submit", "--ref", "GH-1", "--repo", str(repo.path), "--json")
    assert second.exit_code == 0
    assert payload(second)["created"] is False
    assert payload(second)["task"]["id"] == first_payload["task"]["id"]


def test_submit_rejects_an_unknown_kind(paths) -> None:
    result = invoke(paths, "submit", "--ref", "GH-1", "--kind", "carrier-pigeon", "--json")
    assert result.exit_code == 6
    assert payload(result)["error"]["code"] == "config_error"


def test_status_lists_and_refuses_an_unknown_task(paths, repo) -> None:
    submit_cli(paths, repo)
    listed = invoke(paths, "status", "--json")
    assert listed.exit_code == 0
    assert len(payload(listed)["tasks"]) == 1
    missing = invoke(paths, "status", "t-absent", "--json")
    assert missing.exit_code == 5
    assert payload(missing)["error"]["code"] == "not_found"


def test_task_and_trace_verify_the_projection(paths, repo) -> None:
    submitted = submit_cli(paths, repo)
    task_id = submitted["task"]["id"]
    task = invoke(paths, "task", task_id, "--json")
    assert task.exit_code == 0
    assert payload(task)["events"] == 1
    trace = invoke(paths, "trace", task_id, "--json")
    assert trace.exit_code == 0
    assert payload(trace)["events"][0]["type"] == "task.created"


def test_policy_refuses_a_test_edit(paths) -> None:
    result = invoke(paths, "policy", "check", "tests/test_core.py", "--json")
    assert result.exit_code == 3
    body = payload(result)
    assert body["allowed"] is False
    allowed = invoke(paths, "policy", "check", "calc/core.py", "--json")
    assert allowed.exit_code == 0
    assert payload(allowed)["allowed"] is True


def test_dry_run_shows_nodes_and_changes_nothing(paths, repo, scenario_set: Path) -> None:
    submitted = submit_cli(paths, repo)
    task_id = submitted["task"]["id"]
    result = invoke(paths, "run", task_id, "--dry-run", "--scenarios", str(scenario_set), "--json")
    assert result.exit_code == 0, result.stdout + result.stderr
    body = payload(result)
    assert [node["id"] for node in body["nodes"]] == [
        "reproduce",
        "build",
        "test",
        "challenge",
    ]
    assert body["scenario_ids"] == ["add-positive", "add-negative", "mul-positive"]
    assert Queue(paths).load(task_id).state is TaskState.QUEUED


def test_run_without_a_harness_is_a_config_error(paths, repo, scenario_set: Path) -> None:
    submitted = submit_cli(paths, repo)
    result = invoke(
        paths,
        "run",
        submitted["task"]["id"],
        "--approve-plan",
        "--scenarios",
        str(scenario_set),
        "--json",
    )
    assert result.exit_code == 6
    assert payload(result)["error"]["code"] == "config_error"


def test_approve_refuses_a_task_that_is_not_planning(paths, repo) -> None:
    submitted = submit_cli(paths, repo)
    result = invoke(paths, "approve", submitted["task"]["id"], "--json")
    assert result.exit_code == 6


def test_release_approval_is_not_wired_in_v0(paths, repo) -> None:
    submitted = submit_cli(paths, repo)
    result = invoke(paths, "approve", submitted["task"]["id"], "--gate", "release", "--json")
    assert result.exit_code == 2


def test_version_speaks_json(paths) -> None:
    result = invoke(paths, "version", "--json")
    assert result.exit_code == 0
    assert payload(result)["version"] == "0.0.1"


def test_ui_write_and_read_only_are_exclusive(paths) -> None:
    result = invoke(paths, "ui", "--write", "--read-only", "--json")
    assert result.exit_code == 6
    assert "either --write or --read-only" in result.stdout


def test_risk_gate_flake_and_decision_replay(paths, repo, factory_root) -> None:
    submitted = submit_cli(paths, repo)
    task_id = submitted["task"]["id"]
    queue = Queue(paths)
    rating = RiskRating(
        level=RiskLevel.HIGH,
        reasons=["critical path: auth/login.py"],
        owners=["michael"],
        required_reviewers=2,
        deeper_verification=True,
    )
    queue.append(task_id, "risk.rated", rating.model_dump(mode="json"))
    queue.append(task_id, "would_block", {"gate": "policy", "reason": "denied"})
    queue.append(
        task_id,
        "decision.made",
        {"gate": "plan", "action": "ask", "mode": "off"},
    )

    risk = invoke(paths, "risk", task_id, "--json")
    assert risk.exit_code == 0
    assert payload(risk)["risk"]["level"] == "high"

    report = invoke(paths, "gate", "report", "--json")
    assert report.exit_code == 0
    assert payload(report)["report"][0]["gates"]["policy"]["would_block"] == 1

    added = invoke(
        paths,
        "flake",
        "add",
        task_id,
        "--scenario",
        "add-negative",
        "--owner",
        "michael",
        "--reason",
        "times out on Windows",
        "--json",
    )
    assert added.exit_code == 0
    listed = invoke(paths, "flake", "list", "--active", "--json")
    assert listed.exit_code == 0
    assert len(payload(listed)["flakes"]) == 1

    replay = invoke(
        paths,
        "decision",
        "replay",
        "--cases",
        str(factory_root / "fixtures" / "decision-cases.jsonl"),
        "--provider",
        "off",
        "--json",
    )
    assert replay.exit_code == 0
    assert payload(replay)["cases"] == 20


def test_findings_and_metrics_speak_json(paths, repo) -> None:
    submitted = submit_cli(paths, repo)
    task_id = submitted["task"]["id"]
    added = invoke(
        paths,
        "finding",
        "add",
        task_id,
        "--summary",
        "add subtracts",
        "--step",
        "build",
        "--confidence",
        "0.9",
        "--uncertainty",
        "none",
        "--evidence",
        "calc/core.py:5",
        "--json",
    )
    assert added.exit_code == 0, added.stdout
    listed = invoke(paths, "finding", "list", task_id, "--json")
    assert listed.exit_code == 0
    findings = payload(listed)["findings"]
    assert findings and findings[0]["summary"] == "add subtracts"
    metrics = invoke(paths, "metrics", "--json")
    assert metrics.exit_code == 0
    body = payload(metrics)["metrics"]
    assert body["tasks"] == 1
    assert body["per_task"][0]["human_touches"] == 0


def test_schema_and_ledger_speak_json(paths) -> None:
    schema = invoke(paths, "schema", "--json")
    assert schema.exit_code == 0
    assert "task" in json.loads(schema.stdout)["schemas"]
    ledger = invoke(paths, "ledger", "--json")
    assert ledger.exit_code == 0
    assert payload(ledger)["rows"] == []


def test_memory_backfill_has_a_dry_run(paths) -> None:
    result = invoke(paths, "memory", "backfill", "--dry-run", "--json")
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["runs"] == []


def test_doctor_reports_without_crashing(paths, repo) -> None:
    result = invoke(paths, "doctor", "--repo", str(repo.path), "--json")
    assert result.exit_code == 0, result.stdout
    names = {check["name"] for check in payload(result)["checks"]}
    assert {"python", "git", "workspace", "flow"} <= names


def test_the_cli_never_requires_a_tty(paths, repo) -> None:
    submitted = submit_cli(paths, repo)
    result = invoke(paths, "status", submitted["task"]["id"])
    assert result.exit_code == 0
    assert "queued" in result.stdout


def test_an_empty_queue_greets_the_operator_like_a_product(paths) -> None:
    result = invoke(paths, "status")
    assert result.exit_code == 0
    assert "Mira is watching the queue" in result.stdout


def test_a_clean_checkout_is_not_dirty(repo) -> None:
    assert isinstance(repo, GitRepo)
    assert not repo.is_dirty()


def test_import_hardening_drops_the_working_directory() -> None:
    import os
    import sys

    from works.bootstrap import harden_sys_path

    saved = list(sys.path)
    try:
        sys.path.insert(0, os.getcwd())
        sys.path.append("")
        harden_sys_path()
        assert os.getcwd() not in sys.path
        assert "" not in sys.path
    finally:
        sys.path[:] = saved
