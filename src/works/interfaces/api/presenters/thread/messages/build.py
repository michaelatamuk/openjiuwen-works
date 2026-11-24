"""Thread message handlers: the build attempt and its checks."""

from __future__ import annotations

from works.domain.records import Event, Task
from works.interfaces.api.presenters.thread.messages.types import Fields


def _attempt_started(event: Event, task: Task) -> Fields:
    return {
        "role": "builder",
        "title": f"Build attempt {event.data.get('attempt', '?')} started",
        "body": "The builder is editing the disposable worktree.",
    }


def _step_finished(event: Event, task: Task) -> Fields:
    data = event.data
    step = str(data.get("step") or "step")
    code = data.get("exit_code", "?")
    role = "verifier" if step in ("reproduce", "test", "preview", "check") else "builder"
    if step == "reproduce":
        title = "Reproduction confirmed" if code != 0 else "Reproduction did not fail"
        body = (
            "The failing check failed on the base commit, as expected."
            if code != 0
            else "The check passed on the base commit, so the bug was not reproduced."
        )
        tone = "ok" if code != 0 else "bad"
    elif step == "test":
        title = "Tests passed" if code == 0 else "Tests failed"
        body = f"Exit code {code}."
        tone = "ok" if code == 0 else "bad"
    elif step == "preview":
        title = "Preview passed" if code == 0 else "Preview failed"
        body = f"Exit code {code}."
        tone = "ok" if code == 0 else "bad"
    else:
        title = f"{step.capitalize()} finished"
        body = f"Exit code {code}."
        tone = "ok" if code == 0 else "bad"
    return {
        "role": role,
        "title": title,
        "body": body,
        "facts": [step],
        "tone": tone,
    }


def _challenge_decided(event: Event, task: Task) -> Fields:
    data = event.data
    allow = bool(data.get("allow"))
    return {
        "role": "challenger",
        "title": "Independent check allowed" if allow else "Independent check blocked",
        "body": str(data.get("reason") or "No reason recorded."),
        "facts": [f"concerns {len(data.get('concerns') or [])}"],
        "tone": "ok" if allow else "bad",
        "card": {
            "kind": "challenge",
            "rows": [["Allow", "yes" if allow else "no"], ["Model", str(data.get("model", "—"))]],
        },
    }


def _risk_rated(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": f"Risk: {data.get('level', 'unknown')}",
        "body": "; ".join(str(item) for item in (data.get("reasons") or []))
        or "No reasons recorded.",
        "facts": [f"owners {', '.join(data.get('owners') or []) or 'none'}"],
    }


def _decision_made(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": f"Decision: {data.get('verb', '—')}",
        "body": str(data.get("reason_code") or ""),
        "facts": [f"gate {data.get('gate', '—')}"],
    }


def _shadow(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "system",
        "title": "LAIX shadow decision",
        "body": f"{data.get('gate', 'gate')}: {data.get('reason_code', '')}",
        "facts": [f"agree {data.get('agree', '—')}"],
    }


def _finding(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": "Finding recorded",
        "body": str(data.get("summary") or ""),
        "facts": [f"step {data.get('step', '—')}", f"confidence {data.get('confidence', '—')}"],
        "tone": "bad",
    }


def _flake(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": "Flaky test recorded",
        "body": f"{data.get('scenario_id', '?')} has an owner and an expiry.",
        "facts": [f"owner {data.get('owner', '—')}"],
        "tone": "bad",
    }


def _would_block(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": "Observe mode would block",
        "body": f"{data.get('gate', '—')}: {data.get('reason', '')}",
        "tone": "bad",
    }
