from __future__ import annotations

import json

import pytest

from tests.test_release import _proved, _run
from works.agent_chat import (
    ask_mira,
    ask_mira_stream,
    availability,
    build_context,
    generate_commentary,
)
from works.queue import Queue


def test_context_includes_proof_and_release_blockers(paths, monkeypatch) -> None:
    task = _proved(paths)
    _run(paths, task)
    Queue(paths).append(
        task.id,
        "gate.decided",
        {"gate": "plan", "by": "cli", "commit": "abc1234"},
    )

    context = build_context(paths, task.id)

    assert "Verdict: allow" in context
    assert "Proof SHA-256" in context
    assert "Release: not released" in context
    assert "release gate has no human approval" in context


def test_availability_fails_closed_without_a_key(monkeypatch) -> None:
    monkeypatch.delenv("WORKS_MODEL_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    state = availability()

    assert state["available"] is False
    assert "no model key" in state["reason"]


class FakeRun:
    def __init__(self, stdout: str, code: int = 0) -> None:
        self.stdout = stdout
        self.returncode = code
        self.stderr = ""


def test_ask_mira_parses_the_worker_and_records_an_event(paths, monkeypatch) -> None:
    task = _proved(paths)
    _run(paths, task)
    monkeypatch.setattr("works.agent_chat._command", lambda: ["python", "worker.py"])
    monkeypatch.setattr("works.agent_chat._environment", lambda: {})
    monkeypatch.setattr(
        "works.agent_chat.subprocess.run",
        lambda *a, **k: FakeRun(
            json.dumps(
                {
                    "type": "done",
                    "text": "It is not released.",
                    "model": "m",
                    "tokens": 7,
                    "usd": 0.0,
                }
            )
        ),
    )

    answer = ask_mira(paths, task.id, "Is it released?")

    assert answer["text"] == "It is not released."
    events = [event for event in Queue(paths).events(task.id) if event.type == "thread.agent"]
    assert events[-1].data["answer"] == "It is not released."
    assert events[-1].data["tokens"] == 7


class FakeStdin:
    def __init__(self) -> None:
        self.data = ""

    def write(self, value: str) -> None:
        self.data += value

    def close(self) -> None:
        pass


class FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def __iter__(self):
        return iter(self.lines)


class FakeProcess:
    def __init__(self, lines: list[str], code: int = 0) -> None:
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(lines)
        self.returncode = code

    def poll(self) -> int:
        return self.returncode

    def wait(self, timeout: int | None = None) -> int:
        return self.returncode


def test_streaming_yields_deltas_and_records_the_answer(paths, monkeypatch) -> None:
    task = _proved(paths)
    _run(paths, task)
    lines = [
        json.dumps({"type": "start", "model": "m"}),
        json.dumps({"type": "delta", "text": "Not "}),
        json.dumps({"type": "delta", "text": "released."}),
        json.dumps(
            {"type": "done", "text": "Not released.", "model": "m", "tokens": 9, "usd": 0.0}
        ),
    ]
    monkeypatch.setattr("works.agent_chat._command", lambda: ["python", "worker.py"])
    monkeypatch.setattr("works.agent_chat._environment", lambda: {})
    monkeypatch.setattr("works.agent_chat.subprocess.Popen", lambda *a, **k: FakeProcess(lines))

    events = list(ask_mira_stream(paths, task.id, "Is it released?"))

    assert [event["text"] for event in events if event["type"] == "delta"] == ["Not ", "released."]
    assert events[-1]["type"] == "done"
    recorded = [event for event in Queue(paths).events(task.id) if event.type == "thread.agent"]
    assert recorded[-1].data["answer"] == "Not released."


def test_ask_refuses_an_empty_question(paths, monkeypatch) -> None:
    task = _proved(paths)
    _run(paths, task)

    with pytest.raises(Exception, match="question"):
        ask_mira(paths, task.id, "   ")


def test_generate_commentary_records_generated_messages(paths, monkeypatch) -> None:
    task = _proved(paths)
    _run(paths, task)
    monkeypatch.setattr("works.agent_chat._command", lambda: ["python", "worker.py"])
    monkeypatch.setattr("works.agent_chat._environment", lambda: {})
    monkeypatch.setattr(
        "works.agent_chat.subprocess.run",
        lambda *a, **k: FakeRun(
            json.dumps(
                {
                    "type": "done",
                    "messages": [
                        {"role": "builder", "text": "I changed one file."},
                        {"role": "inspector", "text": "The tests passed."},
                        {"role": "reporter", "text": "It is not released."},
                    ],
                    "model": "m",
                    "tokens": 12,
                    "usd": 0.0,
                }
            )
        ),
    )

    result = generate_commentary(paths, task.id)

    assert [item["role"] for item in result] == ["builder", "inspector", "reporter"]
    events = [event for event in Queue(paths).events(task.id) if event.type == "thread.commentary"]
    assert len(events) == 3
    assert events[0].data["generated"] is True
    assert events[0].data["tokens"] == 12
    assert events[1].data["tokens"] == 0
