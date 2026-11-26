from __future__ import annotations

from pathlib import Path

from works.adapters.queue.store import Queue
from works.application.scheduling.policy import POLICY_PATH
from works.application.scheduling.triggers import request_dispatch
from works.domain.records import Source, SourceKind

POLICY = """
enabled: true
allow:
  manual: true
"""


def _policy(paths, text: str = POLICY) -> None:
    path = paths.root / POLICY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _task(paths, *, kind: SourceKind = SourceKind.MANUAL, channel: str | None = None) -> str:
    task, _created = Queue(paths).submit(
        source=Source(kind=kind, ref="R", title="t", channel=channel),
        flow="fix-issue",
        product="P",
        repo=str(Path(paths.root) / "repo"),
    )
    return task.id


def _events(paths, task_id: str, kind: str) -> list:
    return [event for event in Queue(paths).events(task_id) if event.type == kind]


def test_a_disabled_scheduler_refuses_the_request(paths) -> None:
    task_id = _task(paths)

    result = request_dispatch(paths, task_id, remote=False)

    assert result.requested is False
    assert result.reason == "disabled"
    assert _events(paths, task_id, "scheduler.requested") == []


def test_an_allowed_task_records_a_request(paths) -> None:
    _policy(paths)
    task_id = _task(paths)

    result = request_dispatch(paths, task_id, remote=False)

    assert result.requested is True
    assert len(_events(paths, task_id, "scheduler.requested")) == 1


def test_a_remote_client_needs_an_explicit_opt_in(paths) -> None:
    _policy(paths)
    task_id = _task(paths)

    refused = request_dispatch(paths, task_id, remote=True)
    assert refused.requested is False
    assert refused.reason == "remote_trigger"

    _policy(paths, POLICY + "  remote_triggers: true\n")
    allowed = request_dispatch(paths, task_id, remote=True)
    assert allowed.requested is True


def test_a_manual_task_needs_manual_allowed(paths) -> None:
    _policy(paths, "enabled: true\n")
    task_id = _task(paths)

    result = request_dispatch(paths, task_id, remote=False)

    assert result.requested is False
    assert result.reason == "manual_not_allowed"


def test_an_unlisted_source_is_refused(paths) -> None:
    _policy(paths)
    task_id = _task(paths, kind=SourceKind.TRACKER, channel="gitlab")

    result = request_dispatch(paths, task_id, remote=False)

    assert result.requested is False
    assert result.reason == "not_allowlisted"


def test_an_import_without_the_label_is_refused(paths) -> None:
    _policy(paths)
    task_id = _task(paths, kind=SourceKind.TRACKER, channel="github")

    result = request_dispatch(paths, task_id, remote=False)

    assert result.requested is False
    assert result.reason == "missing_label"
