from __future__ import annotations

from datetime import UTC, datetime, timedelta

from works.records import Event, Source, SourceKind, Task, TaskState
from works.ui.server import _pipeline

START = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)


def event(seq: int, kind: str, data: dict) -> Event:
    return Event(seq=seq, ts=START + timedelta(minutes=seq), type=kind, data=data)


def task(state: TaskState) -> Task:
    return Task(
        id="t-demo",
        flow="fix-issue",
        product="DigitalMate",
        repo=".",
        source=Source(kind=SourceKind.MANUAL, ref="DM-1", title="Files are forgotten"),
        state=state,
    )


def events() -> list[Event]:
    return [
        event(1, "task.created", {}),
        event(2, "state.changed", {"to": "reproducing"}),
        event(3, "step.finished", {"step": "reproduce", "exit_code": 1}),
        event(4, "plan.drafted", {"scenario_ids": ["a", "b"]}),
        event(5, "gate.decided", {"gate": "plan", "by": "cli", "commit": "abc"}),
        event(6, "attempt.started", {"attempt": 1}),
        event(7, "step.finished", {"step": "test", "exit_code": 0}),
        event(8, "challenge.decided", {"allow": True}),
        event(9, "state.changed", {"to": "proved"}),
        event(10, "note", {"message": "proof ready"}),
    ]


def evidence(*, allow: bool, stop: str) -> dict:
    return {
        "stop_reason": stop,
        "files_changed": ["calc/core.py"],
        "verdict": {"allow": allow},
        "challenge": {"allow": True},
        "risk": {"level": "low"},
        "model": "fake",
        "proof_sha256": "a" * 64,
    }


def test_a_proved_pipeline_has_five_story_stations() -> None:
    pipeline = _pipeline(task(TaskState.PROVED), events(), evidence(allow=True, stop="completed"))
    labels = [item["label"] for item in pipeline["story"]]
    assert labels == ["Reported", "Confirmed", "Fixed", "Checked", "Release to DigitalMate"]
    assert [item["state"] for item in pipeline["story"]][:4] == ["done", "done", "done", "done"]
    assert pipeline["story"][-1]["state"] == "active"
    assert len(pipeline["technical"]) == 10
    assert pipeline["blocked"] is None


def test_a_blocked_pipeline_explains_why_in_plain_language() -> None:
    pipeline = _pipeline(
        task(TaskState.BLOCKED), events(), evidence(allow=False, stop="verdict_failed")
    )
    checked = next(item for item in pipeline["story"] if item["id"] == "checked")
    assert checked["state"] == "blocked"
    assert checked["caption"] == "Stopped here"
    assert pipeline["blocked"] is not None
    assert "must-pass check failed" in pipeline["blocked"]["why"]
    assert "person" in pipeline["blocked"]["next"]
    assert pipeline["story"][-1]["state"] == "pending"
