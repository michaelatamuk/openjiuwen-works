"""The story line: one caption per person, and the stages behind it."""

from __future__ import annotations

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


def _pipeline(
    task: Task,
    events: list[Event],
    evidence: dict[str, Any] | None,
    delivery: dict[str, Any] | None = None,
    confirmation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A story line and a technical line, both derived from events and evidence."""
    state = task.state.value
    stop = str((evidence or {}).get("stop_reason", ""))
    current = _current_stage(state, stop)
    if confirmation is not None:
        current = 10
    elif delivery is not None:
        current = 9

    plan = next((event.data for event in reversed(events) if event.type == "plan.drafted"), {})
    files = (evidence or {}).get("files_changed") or []
    verdict = (evidence or {}).get("verdict") or {}
    challenge = (evidence or {}).get("challenge") or {}
    risk = (evidence or {}).get("risk") or {}
    gate_plan = _first(events, "gate.decided")
    gate_release = next(
        (
            event
            for event in reversed(events)
            if event.type == "gate.decided" and event.data.get("gate") == "release"
        ),
        None,
    )

    def artifacts(index: int) -> list[str]:
        if index == 0:
            return [f"{task.source.kind.value}:{task.source.ref}", task.source.title]
        if index == 1:
            command = (evidence or {}).get("reproduce") or {}
            return [
                f"exit {command.get('exit_code', '?')}",
                "the problem was reproduced" if command else "not run",
            ]
        if index == 2:
            ids = plan.get("scenario_ids") or []
            return [f"{len(ids)} scenario(s)", "plan drafted"]
        if index == 3:
            if gate_plan is None:
                return ["waiting for a person"]
            return [
                f"by {gate_plan.data.get('by', '?')}",
                f"commit {str(gate_plan.data.get('commit', '?'))[:10]}",
            ]
        if index == 4:
            return [f"{len(files)} file(s) changed", f"model {(evidence or {}).get('model', '—')}"]
        if index == 5:
            return [
                f"verdict {'allow' if verdict.get('allow') else 'block'}",
                f"challenge {'allow' if challenge.get('allow') else 'block'}"
                if challenge
                else "no challenge",
            ]
        if index == 6:
            return [
                f"risk {risk.get('level', '—')}",
                f"proof {str((evidence or {}).get('proof_sha256', ''))[:10]}",
            ]
        if index == 7:
            if gate_release is None:
                return ["waiting for a person" if state == "proved" else "not reached"]
            return [
                f"by {gate_release.data.get('by', '?')}",
                f"commit {str(gate_release.data.get('commit', '?'))[:10]}",
            ]
        if index == 8:
            if delivery is None:
                return ["not delivered" if state == "released" else "not reached"]
            return [
                f"branch {delivery.get('branch', '?')!s}",
                f"commit {str(delivery.get('commit', '?'))[:10]}",
            ]
        if confirmation is None:
            return ["awaiting confirmation"]
        return [
            f"confirmation {'pass' if confirmation.get('ok') else 'fail'}",
            str(confirmation.get("target", "—")),
        ]

    at = [
        _first_at(events, "task.created"),
        _first_at(events, "step.finished", step="reproduce"),
        _first_at(events, "plan.drafted"),
        gate_plan.ts.isoformat() if gate_plan is not None else None,
        _first_at(events, "attempt.started"),
        _first_at(events, "step.finished", step="test")
        or _first_at(events, "step.started", step="test")
        or _first_at(events, "step.started", step="check"),
        next((event.ts.isoformat() for event in reversed(events) if event.type == "note"), None),
        gate_release.ts.isoformat() if gate_release is not None else None,
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
    technical: list[dict[str, Any]] = [
        {
            "id": key,
            "label": label,
            "kind": kind,
            "state": _stage_state(state, current, index),
            "at": at[index],
            "artifacts": artifacts(index),
        }
        for index, (key, label, kind) in enumerate(STAGES)
    ]

    blocked_why = BLOCKED_WHY.get(stop, "The factory stopped before the fix was proven.")
    blocked_key = None
    if state == "blocked":
        blocked_key = next((key for key, _, indexes, _ in STORY if current in indexes), None)
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

    story: list[dict[str, Any]] = []
    for key, label, indexes, caption in STORY:
        states = [technical[index]["state"] for index in indexes]
        if key == "reported":
            stage = "done"
        elif key == "picked_up":
            stage = "done" if current > 0 else "pending"
        elif "blocked" in states:
            stage = "blocked"
        elif all(item == "done" for item in states):
            stage = "done"
        elif any(item == "active" for item in states):
            stage = "active"
        else:
            stage = "pending"
        if key == "delivered":
            if confirmation is not None:
                label = f"Confirmed in {task.product}"
                caption = (
                    f"The released fix was confirmed in {task.product}."
                    if confirmation.get("ok")
                    else f"The confirmation in {task.product} failed."
                )
            elif delivery is not None:
                label = f"Back in {task.product}"
                caption = f"The fix was delivered to {task.product}. Confirmation is next."
            else:
                label = (
                    f"Release to {task.product}"
                    if state == "proved"
                    else f"Deliver to {task.product}"
                )
                caption = (
                    f"The fix is ready to go back to {task.product}."
                    if state == "proved"
                    else f"The fix is released and ready to be delivered to {task.product}."
                    if state == "released"
                    else f"The fix is on its way back to {task.product}."
                )
        story_at = (
            at[0]
            if key == "reported"
            else pickup_at
            if key == "picked_up"
            else next((technical[index]["at"] for index in indexes if technical[index]["at"]), None)
        )
        if key == blocked_key:
            stage = "blocked"
            caption = "Stopped here"
            story_artifacts = ["The fix was not released"]
        elif key == "reported":
            story_artifacts = [
                f"Reported through {SOURCE_LABELS.get(task.source.kind.value, 'the source')}",
                task.source.title,
            ]
        elif key == "picked_up":
            story_artifacts = ["Mira took the report", f"Work started on {task.product}"]
        elif key == "confirmed":
            story_artifacts = [
                "The problem was reproduced",
                "Before the fix, the check failed",
            ]
        elif key == "fixed":
            story_artifacts = [
                "The plan was approved",
                f"{len(files)} file(s) changed",
                "The fix was built",
            ]
        elif key == "checked":
            story_artifacts = (
                [
                    "All must-pass checks passed",
                    "The independent review passed"
                    if challenge.get("allow")
                    else "The independent review found a concern",
                ]
                if verdict.get("allow")
                else [
                    "A must-pass check failed",
                    "The fix is not safe to release",
                ]
            )
        elif key == "delivered":
            if confirmation is not None:
                story_artifacts = [
                    "The released fix was confirmed"
                    if confirmation.get("ok")
                    else "The confirmation failed",
                    str(confirmation.get("target", "—")),
                ]
            elif delivery is not None:
                story_artifacts = [
                    f"Delivered on {delivery.get('branch', 'a branch')}",
                    str(
                        delivery.get("pr_url")
                        or delivery.get("comment_url")
                        or "back to the source"
                    ),
                ]
            else:
                story_artifacts = (
                    ["The fix is released and ready to deliver"]
                    if state == "released"
                    else ["The fix is ready to go back to the source"]
                    if state == "proved"
                    else ["Not delivered yet"]
                )
        else:
            story_artifacts = ["Not reached yet"]
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
                "artifacts": story_artifacts,
            }
        )

    replay = [
        {
            "at": event.ts.isoformat(),
            "stage": _event_stage(event, stop),
            "type": event.type,
            "data": event.data,
        }
        for event in events[-200:]
    ]
    blocked = None
    if state == "blocked":
        failed = [str(item) for item in (verdict.get("p0_failed") or [])]
        check = failed[0].replace("-", " ") if failed else "one must-pass check"
        blocked = {
            "why": blocked_why,
            "next": BLOCKED_NEXT,
            "check": check,
            "impact": f"Nothing was released to {task.product}. The problem is still there.",
        }
    return {
        "story": story,
        "technical": technical,
        "replay": replay,
        "blocked": blocked,
    }
