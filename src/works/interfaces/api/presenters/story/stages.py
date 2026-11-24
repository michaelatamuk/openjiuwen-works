"""The story stages: labels, stage maps and the pure stage helpers."""

from __future__ import annotations

from works.domain.records import Event

CURRENT_BY_STATE = {
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
}


CURRENT_WHEN_BLOCKED = {
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
}


STAGES = [
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


STORY = [
    ("reported", "Reported", [], "A person reported the problem."),
    ("picked_up", "Picked up", [0], "Mira picked it up."),
    ("confirmed", "Confirmed", [1], "We saw it happen."),
    ("fixed", "Fixed", [2, 3, 4], "We built a fix."),
    ("checked", "Checked", [5, 6], "We checked it."),
    ("delivered", "Delivered", [7, 8, 9], "The fix is on its way back."),
]


BLOCKED_WHY = {
    "not_reproducible": "The problem could not be reproduced, so no fix can be proven.",
    "policy_violation": "The change touched a protected area, so the factory stopped.",
    "tests_failed": "A test that must pass failed after the change.",
    "flaky_test": "A test passes only sometimes, so the result cannot be trusted yet.",
    "challenge_failed": "The independent reviewer found a problem the fix did not resolve.",
    "verdict_failed": "A must-pass check failed, so the fix is not safe to release.",
    "budget_exceeded": "The run hit its budget before the fix could be proven.",
    "harness_failed": "The builder could not produce a fix that passed the checks.",
}


BLOCKED_NEXT = (
    "A person needs to review the evidence and decide whether to retry or change the plan."
)


SOURCE_LABELS = {"manual": "a person", "tracker": "the tracker", "detector": "monitoring"}


STATE_STAGES = {
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
}


BLOCKED_STAGES = {
    "not_reproducible": "reproduce",
    "harness_failed": "build",
    "config_error": "build",
    "conflict": "build",
}


STEP_STAGES = {"reproduce": "reproduce", "test": "check", "build": "build"}


def _stage_state(state: str, current: int, index: int) -> str:
    if state == "blocked" and index == current:
        return "blocked"
    if index < current:
        return "done"
    if index == current:
        return "active"
    return "pending"


def _event_stage(event: Event, stop: str) -> str:
    if event.type == "task.created":
        return "signal"
    if event.type == "plan.drafted":
        return "plan"
    if event.type == "gate.decided":
        return "plan_gate" if event.data.get("gate") == "plan" else "release_gate"
    if event.type == "attempt.started":
        return "build"
    if event.type == "step.started":
        return STEP_STAGES.get(str(event.data.get("step")), "signal")
    if event.type == "step.finished":
        step = event.data.get("step")
        return "reproduce" if step == "reproduce" else "check" if step == "test" else "build"
    if event.type == "challenge.decided":
        return "check"
    if event.type == "decision.made":
        gate = event.data.get("gate")
        return "plan_gate" if gate == "plan" else "release_gate" if gate == "release" else "proof"
    if event.type in ("risk.rated", "note"):
        return "proof"
    if event.type == "state.changed":
        target = str(event.data.get("to"))
        if target == "blocked":
            return BLOCKED_STAGES.get(stop, "check")
        return STATE_STAGES.get(target, "confirm")
    return "signal"


def _current_stage(state: str, stop: str) -> int:
    current = CURRENT_BY_STATE.get(state, 0)
    if state == "blocked":
        current = CURRENT_WHEN_BLOCKED.get(stop, 5)
    return current
