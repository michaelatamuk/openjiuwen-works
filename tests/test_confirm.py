from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout

import pytest

from tests.test_deliver import _released, _remote
from works.cli import main
from works.confirm import confirm
from works.deliver import deliver
from works.errors import ConfigError
from works.queue import Queue
from works.records import Source, SourceKind, TaskState


def _delivered(paths, repo, tmp_path):
    task, _worktree, base = _released(paths, repo)
    _remote(tmp_path, repo)
    delivery = deliver(paths, task.id)
    return task, delivery, base


def test_confirmation_runs_a_command_at_the_delivered_commit(paths, repo, tmp_path) -> None:
    task, delivery, _ = _delivered(paths, repo, tmp_path)

    result = confirm(paths, task.id, command=[sys.executable, "-c", "print('ok')"])

    assert result.ok is True
    assert result.created is True
    assert result.commit == delivery.commit
    assert result.target.startswith("command")
    assert (paths.runs / "r-deliver" / "confirmation.json").exists()
    events = [e for e in Queue(paths).events(task.id) if e.type == "confirmation.finished"]
    assert len(events) == 1


def test_confirmation_is_idempotent_and_can_be_forced(paths, repo, tmp_path) -> None:
    task, _, _ = _delivered(paths, repo, tmp_path)
    first = confirm(paths, task.id, command=[sys.executable, "-c", "print('ok')"])

    second = confirm(paths, task.id, command=[sys.executable, "-c", "print('other')"])
    forced = confirm(paths, task.id, command=[sys.executable, "-c", "print('other')"], force=True)

    assert second.created is False
    assert second.output_sha256 == first.output_sha256
    assert forced.created is True
    assert forced.output_sha256 != first.output_sha256


def test_a_failing_command_records_a_failed_confirmation(paths, repo, tmp_path) -> None:
    task, _, _ = _delivered(paths, repo, tmp_path)

    result = confirm(paths, task.id, command=[sys.executable, "-c", "raise SystemExit(3)"])

    assert result.ok is False
    assert result.exit_code == 3


def test_the_http_target_is_used_when_given(monkeypatch, paths, repo, tmp_path) -> None:
    task, _, _ = _delivered(paths, repo, tmp_path)
    monkeypatch.setattr("works.confirm._http_check", lambda url: (True, 204, ""))

    result = confirm(paths, task.id, url="https://example.test/health")

    assert result.ok is True
    assert result.exit_code == 204
    assert result.target == "http https://example.test/health"


def test_the_plan_scenario_set_is_the_default_target(paths, repo, tmp_path) -> None:
    task, _, _ = _delivered(paths, repo, tmp_path)
    scripts = tmp_path / "scenarios"
    scripts.mkdir()
    (scripts / "pass.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    scenario_set = tmp_path / "set.yaml"
    scenario_set.write_text(
        "schema_version: 1\n"
        "flow: fix-issue\n"
        "directory: scenarios\n"
        "scenarios:\n"
        "  - id: p0\n"
        "    priority: P0\n"
        "    script: pass.py\n",
        encoding="utf-8",
    )
    Queue(paths).append(
        task.id, "plan.drafted", {"scenario_set": str(scenario_set), "scenario_ids": ["p0"]}
    )

    result = confirm(paths, task.id)

    assert result.ok is True
    assert result.target == "scenario set (1)"
    assert result.notes == ["p0: pass"]


def test_confirmation_requires_a_delivery(paths, repo) -> None:
    task, _, _ = _released(paths, repo)

    with pytest.raises(ConfigError, match="not been delivered"):
        confirm(paths, task.id, command=[sys.executable, "-c", "pass"])


def test_confirmation_requires_a_release(paths, repo) -> None:
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="GH-NOT-RELEASED", title="not released"),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(repo.path),
    )

    with pytest.raises(ConfigError, match="confirm runs after release"):
        confirm(paths, task.id, command=[sys.executable, "-c", "pass"])


class FakeForge:
    def __init__(self) -> None:
        self.comments: list[dict] = []
        self.closed: list[str] = []

    def ensure_comment(self, *, ref, body, marker):
        self.comments.append({"ref": ref, "body": body, "marker": marker})
        return "https://github.com/owner/name/issues/3#c1"

    def close(self, *, ref):
        self.closed.append(ref)


def test_github_confirmation_comments_and_closes(tmp_path, paths, repo) -> None:
    task, _, _ = _released(paths, repo, ref="owner/name#3")
    _remote(tmp_path, repo)
    deliver(paths, task.id)
    forge = FakeForge()

    result = confirm(
        paths,
        task.id,
        command=[sys.executable, "-c", "print('ok')"],
        tracker="github",
        close_issue=True,
        tracker_client=forge,
    )

    assert result.ok is True
    assert result.comment_url == "https://github.com/owner/name/issues/3#c1"
    assert forge.closed == ["owner/name#3"]
    assert "source issue closed" in result.notes


def test_the_cli_confirms_and_exits_zero(paths, repo, tmp_path) -> None:
    task, _, _ = _delivered(paths, repo, tmp_path)
    out, err = io.StringIO(), io.StringIO()
    command = json.dumps([sys.executable, "-c", "print('ok')"])

    with redirect_stdout(out), redirect_stderr(err):
        code = main(["--home", str(paths.root), "confirm", task.id, "--command", command, "--json"])

    assert code == 0, err.getvalue()
    body = json.loads(out.getvalue().strip().splitlines()[-1])
    assert body["ok"] is True


def test_the_cli_exits_blocked_on_a_failed_confirmation(paths, repo, tmp_path) -> None:
    task, _, _ = _delivered(paths, repo, tmp_path)
    out, err = io.StringIO(), io.StringIO()
    command = json.dumps([sys.executable, "-c", "raise SystemExit(2)"])

    with redirect_stdout(out), redirect_stderr(err):
        code = main(["--home", str(paths.root), "confirm", task.id, "--command", command])

    assert code == 8
    assert "failed" in out.getvalue()
    assert Queue(paths).load(task.id).state is TaskState.RELEASED
