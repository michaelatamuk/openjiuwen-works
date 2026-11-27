from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from tests.unit.application.delivery.test_confirm import _delivered
from works.adapters.queue.store import Queue
from works.application.delivery.confirm import Confirmation
from works.application.monitor import _state_path, monitor
from works.domain.errors import ConfigError


def _confirmation(paths, *, ok: bool = True, code: str = "") -> None:
    run_dir = paths.runs / "r-deliver"
    payload = {
        "task_id": "t",
        "run_id": "r-deliver",
        "commit": "0" * 40,
        "ok": ok,
        "target": "command check",
        "exit_code": 0 if ok else 1,
        "duration_ms": 10,
        "output_sha256": "a" * 64,
        "url": None,
        "command": [sys.executable, "-c", "pass"],
        "screenshots": [],
        "notes": [],
        "comment_url": None,
        "created": True,
        "code": code,
        "unstable": False,
        "deployment_status": None,
        "at": datetime.now(tz=UTC).isoformat(),
    }
    (run_dir / "confirmation.json").write_text(json.dumps(payload), encoding="utf-8")


def _fake(ok: bool, code: str = ""):
    calls: list[bool] = []

    def check(paths, task_id, *, url=None, command=None, force=False, record=True):
        calls.append(record)
        return Confirmation(
            task_id=task_id,
            run_id="r-deliver",
            commit="0" * 40,
            ok=ok,
            target="command check",
            code=code,
            output_sha256="b" * 64,
            at=datetime.now(tz=UTC).isoformat(),
        )

    return check, calls


def test_a_failed_recheck_after_a_pass_files_one_drift_task(paths, repo, tmp_path) -> None:
    task, _delivery, _base = _delivered(paths, repo, tmp_path)
    _confirmation(paths, ok=True)
    check, _calls = _fake(False, "command_failed")

    result = monitor(paths, confirm_fn=check)

    assert result.checked == 1
    assert result.checks[0].drifted is True
    assert len(result.created) == 1
    drift = Queue(paths).load(result.created[0])
    assert drift.source.channel == "drift"
    assert drift.source.severity == "S2"
    assert task.id in (drift.source.reproduction_hint or "")
    assert _state_path(paths, task.id).exists()


def test_the_same_drift_is_not_filed_twice(paths, repo, tmp_path) -> None:
    _task, _delivery, _base = _delivered(paths, repo, tmp_path)
    _confirmation(paths, ok=True)
    check, _calls = _fake(False, "command_failed")

    first = monitor(paths, confirm_fn=check)
    second = monitor(paths, confirm_fn=check)

    assert len(first.created) == 1
    assert second.created == []
    assert second.existing == first.created
    assert len(Queue(paths).list_tasks()) == 2


def test_a_passing_recheck_files_nothing(paths, repo, tmp_path) -> None:
    _delivered(paths, repo, tmp_path)
    _confirmation(paths, ok=True)
    check, _calls = _fake(True)

    result = monitor(paths, confirm_fn=check)

    assert result.checks[0].drifted is False
    assert result.created == []
    assert len(Queue(paths).list_tasks()) == 1


def test_a_baseline_that_already_failed_is_not_a_drift(paths, repo, tmp_path) -> None:
    _delivered(paths, repo, tmp_path)
    _confirmation(paths, ok=False, code="command_failed")
    check, _calls = _fake(False, "command_failed")

    result = monitor(paths, confirm_fn=check)

    assert result.checks[0].drifted is False
    assert result.created == []


def test_a_dry_run_writes_no_task_and_no_state(paths, repo, tmp_path) -> None:
    task, _delivery, _base = _delivered(paths, repo, tmp_path)
    _confirmation(paths, ok=True)
    check, calls = _fake(False, "command_failed")

    result = monitor(paths, confirm_fn=check, dry_run=True)

    assert result.checks[0].drifted is True
    assert result.created == []
    assert calls == [False]
    assert not _state_path(paths, task.id).exists()
    assert len(Queue(paths).list_tasks()) == 1


def test_a_task_without_a_confirmation_is_skipped(paths, repo, tmp_path) -> None:
    task, _delivery, _base = _delivered(paths, repo, tmp_path)
    check, _calls = _fake(False)

    result = monitor(paths, confirm_fn=check)

    assert result.skipped[task.id] == "no_confirmation"
    assert result.created == []


def test_a_failed_check_is_skipped_with_a_reason(paths, repo, tmp_path) -> None:
    task, _delivery, _base = _delivered(paths, repo, tmp_path)
    _confirmation(paths, ok=True)

    def broken(paths, task_id, **kwargs):
        raise ConfigError("the repository is gone")

    result = monitor(paths, confirm_fn=broken)

    assert "repository is gone" in result.skipped[task.id]
    assert result.created == []


def test_the_cli_reports_json(paths, repo, tmp_path, monkeypatch) -> None:
    from tests.unit.interfaces.cli.test_cli import invoke, payload

    _delivered(paths, repo, tmp_path)
    _confirmation(paths, ok=True)
    check, _calls = _fake(False, "command_failed")
    monkeypatch.setattr("works.application.monitor.confirm", check)

    result = invoke(paths, "monitor", "--days", "30", "--json")

    assert result.exit_code == 0, result.stderr
    body = payload(result)
    assert body["checked"] == 1
    assert body["checks"][0]["drifted"] is True
    assert len(body["created"]) == 1
