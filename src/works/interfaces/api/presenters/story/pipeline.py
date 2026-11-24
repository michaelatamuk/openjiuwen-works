"""The story line: one caption per person, and the stages behind it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from works.domain.records import Event, Task
from works.interfaces.api.presenters.story.events import _first, _first_at
from works.interfaces.api.presenters.story.stages import (
    BLOCKED_NEXT,
    BLOCKED_WHY,
    SOURCE_LABELS,
    STAGES,
    STORY,
    _current_stage,
    _event_stage,
    _stage_state,
)


@dataclass(frozen=True)
class _Facts:
    """Everything the two lines read, resolved once from the task and its run."""

    state: str
    stop: str
    current: int
    plan: dict[str, Any]
    files: list[str]
    verdict: dict[str, Any]
    challenge: dict[str, Any]
    risk: dict[str, Any]
    evidence: dict[str, Any] | None
    gate_plan: Event | None
    gate_release: Event | None
    delivery: dict[str, Any] | None
    confirmation: dict[str, Any] | None


def _facts(
    task: Task,
    events: list[Event],
    evidence: dict[str, Any] | None,
    delivery: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
) -> _Facts:
    state = task.state.value
    stop = str((evidence or {}).get("stop_reason", ""))
    current = _current_stage(state, stop)
    if confirmation is not None:
        current = 10
    elif delivery is not None:
        current = 9
    return _Facts(
        state=state,
        stop=stop,
        current=current,
        plan=next((event.data for event in reversed(events) if event.type == "plan.drafted"), {}),
        files=(evidence or {}).get("files_changed") or [],
        verdict=(evidence or {}).get("verdict") or {},
        challenge=(evidence or {}).get("challenge") or {},
        risk=(evidence or {}).get("risk") or {},
        evidence=evidence,
        gate_plan=_first(events, "gate.decided"),
        gate_release=next(
            (
                event
                for event in reversed(events)
                if event.type == "gate.decided" and event.data.get("gate") == "release"
            ),
            None,
        ),
        delivery=delivery,
        confirmation=confirmation,
    )


def _stage_artifacts(facts: _Facts, task: Task, index: int) -> list[str]:
    if index == 0:
        return [f"{task.source.kind.value}:{task.source.ref}", task.source.title]
    if index == 1:
        command = (facts.evidence or {}).get("reproduce") or {}
        return [
            f"exit {command.get('exit_code', '?')}",
            "the problem was reproduced" if command else "not run",
        ]
    if index == 2:
        ids = facts.plan.get("scenario_ids") or []
        return [f"{len(ids)} scenario(s)", "plan drafted"]
    if index == 3:
        if facts.gate_plan is None:
            return ["waiting for a person"]
        return [
            f"by {facts.gate_plan.data.get('by', '?')}",
            f"commit {str(facts.gate_plan.data.get('commit', '?'))[:10]}",
        ]
    if index == 4:
        return [
            f"{len(facts.files)} file(s) changed",
            f"model {(facts.evidence or {}).get('model', '—')}",
        ]
    if index == 5:
        return [
            f"verdict {'allow' if facts.verdict.get('allow') else 'block'}",
            f"challenge {'allow' if facts.challenge.get('allow') else 'block'}"
            if facts.challenge
            else "no challenge",
        ]
    if index == 6:
        return [
            f"risk {facts.risk.get('level', '—')}",
            f"proof {str((facts.evidence or {}).get('proof_sha256', ''))[:10]}",
        ]
    if index == 7:
        if facts.gate_release is None:
            return ["waiting for a person" if facts.state == "proved" else "not reached"]
        return [
            f"by {facts.gate_release.data.get('by', '?')}",
            f"commit {str(facts.gate_release.data.get('commit', '?'))[:10]}",
        ]
    if index == 8:
        if facts.delivery is None:
            return ["not delivered" if facts.state == "released" else "not reached"]
        return [
            f"branch {facts.delivery.get('branch', '?')!s}",
            f"commit {str(facts.delivery.get('commit', '?'))[:10]}",
        ]
    if facts.confirmation is None:
        return ["awaiting confirmation"]
    return [
        f"confirmation {'pass' if facts.confirmation.get('ok') else 'fail'}",
        str(facts.confirmation.get("target", "—")),
    ]


def _timeline(events: list[Event], facts: _Facts) -> tuple[list[str | None], str | None]:
    at: list[str | None] = [
        _first_at(events, "task.created"),
        _first_at(events, "step.finished", step="reproduce"),
        _first_at(events, "plan.drafted"),
        facts.gate_plan.ts.isoformat() if facts.gate_plan is not None else None,
        _first_at(events, "attempt.started"),
        _first_at(events, "step.finished", step="test")
        or _first_at(events, "step.started", step="test")
        or _first_at(events, "step.started", step="check"),
        next((event.ts.isoformat() for event in reversed(events) if event.type == "note"), None),
        facts.gate_release.ts.isoformat() if facts.gate_release is not None else None,
        next(
            (
                event.ts.isoformat()
                for event in events
                if event.type == "state.changed" and event.data.get("to") == "released"
            ),
            None,
        ),
        next(
            (
                event.ts.isoformat()
                for event in reversed(events)
                if event.type == "delivery.finished"
            ),
            None,
        ),
        next(
            (
                event.ts.isoformat()
                for event in reversed(events)
                if event.type == "confirmation.finished"
            ),
            None,
        ),
    ]
    pickup_at = (
        next(
            (
                event.ts.isoformat()
                for event in events
                if event.type == "state.changed" and event.data.get("to") == "reproducing"
            ),
            None,
        )
        or at[1]
    )
    return at, pickup_at


def _technical(facts: _Facts, task: Task, at: list[str | None]) -> list[dict[str, Any]]:
    return [
        {
            "id": key,
            "label": label,
            "kind": kind,
            "state": _stage_state(facts.state, facts.current, index),
            "at": at[index],
            "artifacts": _stage_artifacts(facts, task, index),
        }
        for index, (key, label, kind) in enumerate(STAGES)
    ]


def _story_stage(key: str, states: list[str], facts: _Facts) -> str:
    if key == "reported":
        return "done"
    if key == "picked_up":
        return "done" if facts.current > 0 else "pending"
    if "blocked" in states:
        return "blocked"
    if all(item == "done" for item in states):
        return "done"
    if any(item == "active" for item in states):
        return "active"
    return "pending"


def _delivery_copy(task: Task, facts: _Facts) -> tuple[str, str]:
    if facts.confirmation is not None:
        ok = facts.confirmation.get("ok")
        return (
            f"Confirmed in {task.product}",
            (
                f"The released fix was confirmed in {task.product}."
                if ok
                else f"The confirmation in {task.product} failed."
            ),
        )
    if facts.delivery is not None:
        return (
            f"Back in {task.product}",
            f"The fix was delivered to {task.product}. Confirmation is next.",
        )
    label = (
        f"Release to {task.product}" if facts.state == "proved" else f"Deliver to {task.product}"
    )
    caption = (
        f"The fix is ready to go back to {task.product}."
        if facts.state == "proved"
        else f"The fix is released and ready to be delivered to {task.product}."
        if facts.state == "released"
        else f"The fix is on its way back to {task.product}."
    )
    return label, caption


def _delivery_artifacts(facts: _Facts) -> list[str]:
    if facts.confirmation is not None:
        return [
            "The released fix was confirmed"
            if facts.confirmation.get("ok")
            else "The confirmation failed",
            str(facts.confirmation.get("target", "—")),
        ]
    if facts.delivery is not None:
        return [
            f"Delivered on {facts.delivery.get('branch', 'a branch')}",
            str(
                facts.delivery.get("pr_url")
                or facts.delivery.get("comment_url")
                or "back to the source"
            ),
        ]
    return (
        ["The fix is released and ready to deliver"]
        if facts.state == "released"
        else ["The fix is ready to go back to the source"]
        if facts.state == "proved"
        else ["Not delivered yet"]
    )


def _story_block(key: str, facts: _Facts, task: Task, blocked_key: str | None) -> list[str]:
    if key == blocked_key:
        return ["The fix was not released"]
    if key == "reported":
        return [
            f"Reported through {SOURCE_LABELS.get(task.source.kind.value, 'the source')}",
            task.source.title,
        ]
    if key == "picked_up":
        return ["Mira took the report", f"Work started on {task.product}"]
    if key == "confirmed":
        return [
            "The problem was reproduced",
            "Before the fix, the check failed",
        ]
    if key == "fixed":
        return [
            "The plan was approved",
            f"{len(facts.files)} file(s) changed",
            "The fix was built",
        ]
    if key == "checked":
        return (
            [
                "All must-pass checks passed",
                "The independent review passed"
                if facts.challenge.get("allow")
                else "The independent review found a concern",
            ]
            if facts.verdict.get("allow")
            else [
                "A must-pass check failed",
                "The fix is not safe to release",
            ]
        )
    if key == "delivered":
        return _delivery_artifacts(facts)
    return ["Not reached yet"]


def _story(
    facts: _Facts,
    task: Task,
    technical: list[dict[str, Any]],
    at: list[str | None],
    pickup_at: str | None,
) -> list[dict[str, Any]]:
    blocked_key = None
    if facts.state == "blocked":
        blocked_key = next((key for key, _, indexes, _ in STORY if facts.current in indexes), None)
    story: list[dict[str, Any]] = []
    for key, label, indexes, caption in STORY:
        states = [technical[index]["state"] for index in indexes]
        stage = _story_stage(key, states, facts)
        if key == "delivered":
            label, caption = _delivery_copy(task, facts)
        if key == blocked_key:
            stage = "blocked"
            caption = "Stopped here"
        story_at = (
            at[0]
            if key == "reported"
            else pickup_at
            if key == "picked_up"
            else next((technical[index]["at"] for index in indexes if technical[index]["at"]), None)
        )
        story.append(
            {
                "id": key,
                "label": label,
                "kind": "source"
                if key == "reported"
                else "gate"
                if key == "delivered"
                else "stage",
                "state": stage,
                "at": story_at,
                "caption": caption,
                "artifacts": _story_block(key, facts, task, blocked_key),
            }
        )
    return story


def _replay(events: list[Event], stop: str) -> list[dict[str, Any]]:
    return [
        {
            "at": event.ts.isoformat(),
            "stage": _event_stage(event, stop),
            "type": event.type,
            "data": event.data,
        }
        for event in events[-200:]
    ]


def _blocked(facts: _Facts, task: Task) -> dict[str, Any] | None:
    if facts.state != "blocked":
        return None
    failed = [str(item) for item in (facts.verdict.get("p0_failed") or [])]
    check = failed[0].replace("-", " ") if failed else "one must-pass check"
    return {
        "why": BLOCKED_WHY.get(facts.stop, "The factory stopped before the fix was proven."),
        "next": BLOCKED_NEXT,
        "check": check,
        "impact": f"Nothing was released to {task.product}. The problem is still there.",
    }


def _pipeline(
    task: Task,
    events: list[Event],
    evidence: dict[str, Any] | None,
    delivery: dict[str, Any] | None = None,
    confirmation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A story line and a technical line, both derived from events and evidence."""
    facts = _facts(task, events, evidence, delivery, confirmation)
    at, pickup_at = _timeline(events, facts)
    technical = _technical(facts, task, at)
    return {
        "story": _story(facts, task, technical, at, pickup_at),
        "technical": technical,
        "replay": _replay(events, facts.stop),
        "blocked": _blocked(facts, task),
    }
