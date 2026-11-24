"""HTTP API presenters and runtime helpers."""

from __future__ import annotations

from typing import Any

from works.domain.records import Event, Task


def _first(events: list[Event], kind: str, *, step: str | None = None) -> Event | None:
    for event in events:
        if event.type != kind:
            continue
        if step is not None and event.data.get("step") != step:
            continue
        return event
    return None


def _first_at(events: list[Event], kind: str, *, step: str | None = None) -> str | None:
    event = _first(events, kind, step=step)
    return event.ts.isoformat() if event is not None else None


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
    current = {
        "queued": 0,
        "reproducing": 1,
        "reproduced": 2,
        "planning": 2,
        "plan_approved": 4,
        "building": 4,
        "checking": 5,
        "proved": 7,
        "releasing": 7,
        "released": 8,
    }.get(state, 0)
    if confirmation is not None:
        current = 10
    elif delivery is not None:
        current = 9
    if state == "blocked":
        current = {
            "not_reproducible": 1,
            "policy_violation": 5,
            "tests_failed": 5,
            "flaky_test": 5,
            "budget_exceeded": 5,
            "challenge_failed": 6,
            "verdict_failed": 6,
            "harness_failed": 4,
            "config_error": 4,
            "conflict": 4,
        }.get(stop, 5)

    specs = [
        ("signal", "Read the signal", "source"),
        ("reproduce", "Reproduce", "agent"),
        ("plan", "Plan", "agent"),
        ("plan_gate", "Plan approved", "gate"),
        ("build", "Build", "agent"),
        ("check", "Check", "verify"),
        ("proof", "Proof", "artifact"),
        ("release_gate", "Release approved", "gate"),
        ("deliver", "Deliver", "source"),
        ("confirm", "Confirm", "verify"),
    ]
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

    def stage_state(index: int) -> str:
        if state == "blocked" and index == current:
            return "blocked"
        if index < current:
            return "done"
        if index == current:
            return "active"
        return "pending"

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
            "state": stage_state(index),
            "at": at[index],
            "artifacts": artifacts(index),
        }
        for index, (key, label, kind) in enumerate(specs)
    ]

    story_specs = [
        ("reported", "Reported", [], "A person reported the problem."),
        ("picked_up", "Picked up", [0], "Mira picked it up."),
        ("confirmed", "Confirmed", [1], "We saw it happen."),
        ("fixed", "Fixed", [2, 3, 4], "We built a fix."),
        ("checked", "Checked", [5, 6], "We checked it."),
        ("delivered", "Delivered", [7, 8, 9], "The fix is on its way back."),
    ]
    blocked_why = {
        "not_reproducible": "The problem could not be reproduced, so no fix can be proven.",
        "policy_violation": "The change touched a protected area, so the factory stopped.",
        "tests_failed": "A test that must pass failed after the change.",
        "flaky_test": "A test passes only sometimes, so the result cannot be trusted yet.",
        "challenge_failed": "The independent reviewer found a problem the fix did not resolve.",
        "verdict_failed": "A must-pass check failed, so the fix is not safe to release.",
        "budget_exceeded": "The run hit its budget before the fix could be proven.",
        "harness_failed": "The builder could not produce a fix that passed the checks.",
    }.get(stop, "The factory stopped before the fix was proven.")
    blocked_next = (
        "A person needs to review the evidence and decide whether to retry or change the plan."
    )
    blocked_key = None
    if state == "blocked":
        blocked_key = next((key for key, _, indexes, _ in story_specs if current in indexes), None)
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
    for key, label, indexes, caption in story_specs:
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
            source = {"manual": "a person", "tracker": "the tracker", "detector": "monitoring"}
            story_artifacts = [
                f"Reported through {source.get(task.source.kind.value, 'the source')}",
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

    def event_stage(event: Event) -> str:
        if event.type == "task.created":
            return "signal"
        if event.type == "plan.drafted":
            return "plan"
        if event.type == "gate.decided":
            return "plan_gate" if event.data.get("gate") == "plan" else "release_gate"
        if event.type == "attempt.started":
            return "build"
        if event.type == "step.started":
            return {"reproduce": "reproduce", "test": "check", "build": "build"}.get(
                str(event.data.get("step")), "signal"
            )
        if event.type == "step.finished":
            step = event.data.get("step")
            return "reproduce" if step == "reproduce" else "check" if step == "test" else "build"
        if event.type == "challenge.decided":
            return "check"
        if event.type == "decision.made":
            gate = event.data.get("gate")
            return (
                "plan_gate" if gate == "plan" else "release_gate" if gate == "release" else "proof"
            )
        if event.type in ("risk.rated", "note"):
            return "proof"
        if event.type == "state.changed":
            target = str(event.data.get("to"))
            if target == "blocked":
                return {
                    "not_reproducible": "reproduce",
                    "harness_failed": "build",
                    "config_error": "build",
                    "conflict": "build",
                }.get(stop, "check")
            return {
                "queued": "signal",
                "reproducing": "reproduce",
                "reproduced": "reproduce",
                "planning": "plan",
                "plan_approved": "plan_gate",
                "building": "build",
                "checking": "check",
                "proved": "proof",
                "releasing": "release_gate",
                "released": "deliver",
                "reverted": "deliver",
            }.get(target, "confirm")
        return "signal"

    replay = [
        {
            "at": event.ts.isoformat(),
            "stage": event_stage(event),
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
            "next": blocked_next,
            "check": check,
            "impact": f"Nothing was released to {task.product}. The problem is still there.",
        }
    return {
        "story": story,
        "technical": technical,
        "replay": replay,
        "blocked": blocked,
    }
