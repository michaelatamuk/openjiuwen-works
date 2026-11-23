from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests.test_release import _proved
from works.adapters.queue.store import Queue
from works.domain.records import Event
from works.interfaces.api.server import _thread_message, _thread_rail


def event(kind: str, data: dict | None = None, seq: int = 1) -> Event:
    return Event(seq=seq, ts=datetime.now(tz=UTC), type=kind, data=data or {})


@pytest.mark.parametrize(
    ("kind", "data", "role", "title", "tone"),
    [
        (
            "plan.drafted",
            {"scenario_ids": ["a"], "p0": ["a"], "p1": []},
            "builder",
            "Plan drafted",
            "",
        ),
        (
            "gate.decided",
            {"gate": "plan", "by": "cli", "commit": "abc"},
            "person",
            "Plan approved",
            "ok",
        ),
        (
            "gate.decided",
            {"gate": "release", "by": "cli", "commit": "abc"},
            "person",
            "Release approved",
            "ok",
        ),
        ("attempt.started", {"attempt": 2}, "builder", "Build attempt 2 started", ""),
        (
            "step.finished",
            {"step": "reproduce", "exit_code": 1},
            "verifier",
            "Reproduction confirmed",
            "ok",
        ),
        ("step.finished", {"step": "test", "exit_code": 0}, "verifier", "Tests passed", "ok"),
        ("step.finished", {"step": "preview", "exit_code": 1}, "verifier", "Preview failed", "bad"),
        ("step.finished", {"step": "build", "exit_code": 0}, "builder", "Build finished", "ok"),
        (
            "challenge.decided",
            {"allow": False, "reason": "no test"},
            "challenger",
            "Independent check blocked",
            "bad",
        ),
        (
            "risk.rated",
            {"level": "high", "reasons": ["auth"], "owners": ["m"]},
            "verifier",
            "Risk: high",
            "",
        ),
        (
            "decision.made",
            {"verb": "ask", "reason_code": "x", "gate": "plan"},
            "verifier",
            "Decision: ask",
            "",
        ),
        (
            "finding",
            {"summary": "bug", "step": "check", "confidence": 0.9},
            "verifier",
            "Finding recorded",
            "bad",
        ),
        ("flake", {"scenario_id": "p0", "owner": "m"}, "verifier", "Flaky test recorded", "bad"),
        (
            "would_block",
            {"gate": "release", "reason": "no owner"},
            "verifier",
            "Observe mode would block",
            "bad",
        ),
        (
            "readiness.checked",
            {"status": "fail", "passed": 1, "total": 2},
            "verifier",
            "Readiness: fail",
            "bad",
        ),
        (
            "team.verified",
            {"verdict": "allow", "blockers": []},
            "team",
            "Team verdict: allow",
            "ok",
        ),
        (
            "delivery.finished",
            {"branch": "works/t", "commit": "abc", "pushed": True, "provider": "github"},
            "delivery",
            "Delivered",
            "ok",
        ),
        (
            "confirmation.finished",
            {"ok": False, "target": "http x", "exit_code": 5},
            "confirmation",
            "Confirmation failed",
            "bad",
        ),
        ("thread.note", {"message": "context", "by": "person"}, "person", "Context added", ""),
        (
            "decision.shadow",
            {"gate": "plan", "reason_code": "x", "agree": True},
            "system",
            "LAIX shadow decision",
            "",
        ),
        ("wait.started", {"on": "review", "wake_on": "x"}, "system", "Waiting", ""),
        ("memory.reported", {"via": "run"}, "system", "PPMA synced", ""),
        ("memory.failed", {"error": "down"}, "system", "PPMA failed", "bad"),
        ("state.changed", {"to": "blocked", "reason": "x"}, "system", "State: blocked", "bad"),
        ("preview.finished", {"exit_code": 0}, "verifier", "Preview finished", "ok"),
    ],
)
def test_thread_messages_map_real_events(paths, kind, data, role, title, tone) -> None:
    task = _proved(paths)
    message = _thread_message(event(kind, data), task)
    assert message is not None
    assert message["role"] == role
    assert message["title"] == title
    assert message["tone"] == tone


def test_a_proposal_note_is_a_builder_message(paths) -> None:
    task = _proved(paths)
    message = _thread_message(
        event("note", {"message": "proposal received", "model": "m", "paths": ["a.py"]}), task
    )
    assert message is not None
    assert message["role"] == "builder"
    assert message["title"] == "Proposal received"
    assert "a.py" in message["facts"]


def test_the_old_v0_note_is_rewritten(paths) -> None:
    task = _proved(paths)
    message = _thread_message(
        event("note", {"message": "release gate not crossed in v0; proof is ready"}), task
    )
    assert message is not None
    assert message["title"] == "Proof ready"
    assert "gate 2" in message["body"]


def test_non_thread_state_changes_are_skipped(paths) -> None:
    task = _proved(paths)
    assert _thread_message(event("state.changed", {"to": "planning"}), task) is None
    assert _thread_message(event("unknown.event"), task) is None


def test_the_rail_collects_people_agents_and_checks(paths) -> None:
    task = _proved(paths)
    events = [
        event("gate.decided", {"gate": "plan", "by": "michael"}, 1),
        event("gate.decided", {"gate": "release", "by": "anna"}, 2),
    ]
    run = {"run_id": "r-1", "base_commit": "abc1234", "checks_sha": "c" * 64}
    evidence = {
        "model": "m",
        "provider": "p",
        "tokens": 10,
        "usd": 0.1,
        "duration_ms": 100,
        "policy": {"ok": True},
        "verdict": {"allow": True},
        "challenge": {"allow": True, "model": "c"},
        "risk": {"owners": ["owner"]},
        "proof_sha256": "a" * 64,
    }
    rail = _thread_rail(
        task,
        events,
        run,
        evidence,
        {"released": False},
        {"branch": "works/t", "commit": "abc1234", "pr_url": "https://x"},
        {"ok": True},
        {"latest": {"verdict": "allow"}},
        {"name": "docker", "isolation": "container"},
    )
    assert rail["people"] == ["anna", "michael"]
    assert rail["owners"] == ["owner"]
    assert any(
        agent["role"] == "verifier" and agent["name"] == "docker" for agent in rail["agents"]
    )
    assert rail["cost"]["tokens"] == 10
    assert any(
        item["label"] == "Confirmation" and item["value"] == "pass" for item in rail["checks"]
    )


def test_add_context_event_is_projectable(paths) -> None:
    task = _proved(paths)
    queue = Queue(paths)
    queue.append(task.id, "thread.note", {"message": "hello", "by": "person"})
    assert queue.load(task.id).updated_at >= task.updated_at


def test_commentary_is_marked_as_generated(paths) -> None:
    task = _proved(paths)
    message = _thread_message(
        event(
            "thread.commentary",
            {"role": "builder", "text": "One file changed.", "model": "m", "generated": True},
        ),
        task,
    )
    assert message is not None
    assert message["role"] == "builder"
    assert message["title"] == "Builder commentary"
    assert message["generated"] is True
    assert "AI commentary" in message["facts"]


def test_discussion_is_labelled_distinctly_from_commentary(paths) -> None:
    task = _proved(paths)
    message = _thread_message(
        event(
            "thread.discussion",
            {
                "role": "challenger",
                "stance": "block",
                "text": "Mobile is untested.",
                "model": "m",
                "generated": True,
            },
        ),
        task,
    )
    assert message is not None
    assert message["role"] == "challenger"
    assert message["title"] == "Challenger discusses"
    assert message["generated"] is True
    assert message["generated_label"] == "AI discussion"
    assert message["stance"] == "block"
    assert "AI discussion" in message["facts"]
