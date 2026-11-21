from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from tests.test_evidence import fixed_evidence
from works.memory import EVENT_TYPE, PpmaMemory, ulid_for
from works.records import RunRecord, Source, SourceKind, StopReason, Task, TaskState

ULID = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None, dict[str, str]]] = []
        self.unauthorized_once = False

    def __call__(
        self, method: str, url: str, body: dict[str, Any] | None, headers: dict[str, str]
    ) -> tuple[int, Any]:
        self.calls.append((method, url, body, headers))
        if url.endswith("/manifest"):
            return 200, {"app": "works", "version": "0.0.1"}
        if url.endswith("/token"):
            return 200, {"app": "works", "token": "app-token"}
        if self.unauthorized_once:
            self.unauthorized_once = False
            return 401, {"error": "expired"}
        return 202, {"accepted": ["id"], "duplicates": []}


def make_record(evidence) -> tuple[Task, RunRecord]:
    task = Task(
        id="t-1",
        flow="fix-issue",
        product="openjiuwen",
        repo=".",
        source=Source(kind=SourceKind.MANUAL, ref="GH-1", title="bug"),
    )
    now = datetime.now(tz=UTC)
    record = RunRecord(
        run_id=evidence.run_id,
        task_id=task.id,
        flow="fix-issue",
        state=TaskState.PROVED,
        stop_reason=StopReason.COMPLETED,
        started_at=now,
        finished_at=now,
    )
    return task, record


def test_run_ids_become_deterministic_valid_ulids() -> None:
    first = ulid_for("r-1")
    assert first == ulid_for("r-1")
    assert first != ulid_for("r-2")
    assert ULID.match(first)


def test_a_finished_run_is_reported_through_manifest_token_and_event() -> None:
    transport = FakeTransport()
    memory = PpmaMemory(
        "http://ppma",
        transport=transport,
        owner_token="owner",  # noqa: S106 - a test token
    )
    evidence = fixed_evidence().bind()
    task, record = make_record(evidence)
    memory.record(task=task, record=record, evidence=evidence)

    methods = [call[0] for call in transport.calls]
    assert methods == ["PUT", "POST", "POST"]
    assert transport.calls[0][1].endswith("/v0/apps/works/manifest")
    assert transport.calls[1][1].endswith("/v0/apps/works/token")
    assert transport.calls[2][1].endswith("/v0/spaces/me/messages")
    batch = transport.calls[2][2]
    assert batch is not None and len(batch["messages"]) == 1
    message = batch["messages"][0]
    assert message["type"] == EVENT_TYPE
    assert message["payload"]["run_id"] == evidence.run_id
    assert message["payload"]["verdict"] == "allow"
    assert message["id"] == ulid_for(evidence.run_id)
    assert transport.calls[2][3]["Authorization"] == "Bearer app-token"


def test_the_same_run_has_the_same_message_id() -> None:
    evidence = fixed_evidence().bind()
    task, record = make_record(evidence)
    first = PpmaMemory("http://ppma", transport=FakeTransport())
    second = PpmaMemory("http://ppma", transport=FakeTransport())
    first.record(task=task, record=record, evidence=evidence)
    second.record(task=task, record=record, evidence=evidence)
    assert (
        first._message(task, record, evidence)["id"]
        == second._message(task, record, evidence)["id"]
    )


def test_a_rotated_token_is_minted_again_and_the_event_retried() -> None:
    transport = FakeTransport()
    transport.unauthorized_once = True
    memory = PpmaMemory(
        "http://ppma",
        transport=transport,
        owner_token="owner",  # noqa: S106 - a test token
    )
    evidence = fixed_evidence().bind()
    task, record = make_record(evidence)
    memory.record(task=task, record=record, evidence=evidence)
    assert [call[0] for call in transport.calls] == [
        "PUT",
        "POST",
        "POST",
        "PUT",
        "POST",
        "POST",
    ]
    assert transport.calls[-1][2]["messages"][0]["id"] == ulid_for(evidence.run_id)


def test_a_refused_event_is_an_error_but_memory_is_still_optional() -> None:
    def refuse(method: str, url: str, body: Any, headers: dict[str, str]):
        if url.endswith("/manifest"):
            return 200, {}
        if url.endswith("/token"):
            return 200, {"token": "t"}
        return 500, {"error": "down"}

    memory = PpmaMemory("http://ppma", transport=refuse)
    evidence = fixed_evidence().bind()
    task, record = make_record(evidence)
    try:
        memory.record(task=task, record=record, evidence=evidence)
    except RuntimeError as exc:
        assert "500" in str(exc)
    else:
        raise AssertionError("a refused event must raise")
