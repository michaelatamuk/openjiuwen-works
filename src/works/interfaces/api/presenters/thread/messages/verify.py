"""Thread message handlers: readiness, the team, preview and state moves."""

from __future__ import annotations

from works.domain.records import Event, Task
from works.interfaces.api.presenters.thread.messages.types import Fields


def _readiness(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": f"Readiness: {data.get('status', '—')}",
        "body": f"{data.get('passed', '?')} of {data.get('total', '?')} checks passed.",
        "facts": [str(data.get("note") or "")],
        "tone": "ok" if data.get("status") == "pass" else "bad",
    }


def _team_verified(event: Event, task: Task) -> Fields:
    data = event.data
    verdict = str(data.get("verdict") or "?")
    blockers = data.get("blockers") or []
    inspector = data.get("inspector") or {}
    challenger = data.get("challenger") or {}
    inspector_text = (
        ("allow" if inspector.get("allow") else "block") if inspector else "not recorded"
    )
    challenger_text = (
        ("allow" if challenger.get("allow") else "block") if challenger else "not recorded"
    )
    return {
        "role": "team",
        "title": f"Team verdict: {verdict}",
        "body": "; ".join(str(item) for item in blockers) or "No blockers.",
        "facts": [f"inspector {inspector_text}", f"challenger {challenger_text}"],
        "tone": "ok" if verdict == "allow" else "bad",
        "card": {
            "kind": "team",
            "rows": [
                ["Verdict", verdict],
                ["Inspector", inspector_text],
                ["Challenger", challenger_text],
            ],
        },
    }


def _preview(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": "Preview finished",
        "body": f"Exit code {data.get('exit_code', '?')}.",
        "tone": "ok" if data.get("exit_code") == 0 else "bad",
    }


def _state_changed(event: Event, task: Task) -> Fields | None:
    data = event.data
    target = str(data.get("to") or "")
    if target not in ("blocked", "released", "reverted"):
        return None
    return {
        "role": "system",
        "title": f"State: {target}",
        "body": str(data.get("reason") or ""),
        "tone": "bad" if target in ("blocked", "reverted") else "ok",
    }
