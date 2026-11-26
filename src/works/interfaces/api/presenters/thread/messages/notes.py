"""Thread message handlers: notes, AI turns, waits and memory."""

from __future__ import annotations

from typing import Any

from works.domain.records import Event, Task
from works.interfaces.api.presenters.thread.messages.types import Fields


def _agent(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "mira",
        "title": "Mira answered",
        "body": str(data.get("answer") or ""),
        "facts": [
            f"model {data.get('model') or '-'}",
            f"{data.get('tokens') or 0} token(s)",
        ],
        "generated": True,
        "generated_label": "AI answer",
        "card": {
            "kind": "question",
            "rows": [["Question", str(data.get("question") or "")]],
        },
    }


def _commentary(event: Event, task: Task) -> Fields:
    data = event.data
    role = str(data.get("role") or "mira")
    return {
        "role": role,
        "title": {
            "builder": "Builder commentary",
            "inspector": "Inspector commentary",
            "reporter": "Reporter commentary",
        }.get(role, "Mira commentary"),
        "body": str(data.get("text") or ""),
        "facts": ["AI commentary", f"model {data.get('model') or '-'}"],
        "generated": True,
        "generated_label": "AI commentary",
    }


def _discussion(event: Event, task: Task) -> Fields:
    data = event.data
    role = str(data.get("role") or "mira")
    return {
        "role": role,
        "title": {
            "inspector": "Inspector discusses",
            "challenger": "Challenger discusses",
            "reporter": "Reporter discusses",
        }.get(role, "Team discussion"),
        "body": str(data.get("text") or ""),
        "stance": str(data.get("stance") or ""),
        "facts": ["AI discussion", f"model {data.get('model') or '-'}"],
        "generated": True,
        "generated_label": "AI discussion",
    }


def _thread_note(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "person",
        "title": "Context added",
        "body": str(data.get("message") or ""),
        "facts": [f"by {data.get('by', 'a person')}"],
    }


def _note(event: Event, task: Task) -> Fields:
    data = event.data
    raw_body = str(data.get("message") or "")
    if data.get("model"):
        paths = data.get("paths") or []
        return {
            "role": "builder",
            "title": "Proposal received",
            "body": f"{data.get('model')} proposed a change to {len(paths)} file(s).",
            "facts": [str(item) for item in paths],
        }
    if "v0" in raw_body and "release gate" in raw_body:
        options: list[dict[str, Any]] = [{"label": "Open run", "action": "open-run"}]
        if task.state.value == "proved":
            options.insert(
                0,
                {
                    "label": "Release this commit",
                    "action": "release",
                    "tone": "primary",
                    "recommended": True,
                },
            )
        options.insert(1, {"label": "Open release", "action": "open-release"})
        return {
            "role": "system",
            "title": "Proof ready",
            "body": "proof is ready; gate 2 is the next step",
            "card": {
                "kind": "question",
                "prompt": "Release this commit?",
                "options": options,
            },
        }
    return {"role": "system", "title": "Note", "body": raw_body}


def _reporter_replied(event: Event, task: Task) -> Fields:
    data = event.data
    reopened = bool(data.get("reopened"))
    facts = [f"by {data.get('author') or 'a reporter'}"]
    if data.get("previous_run"):
        facts.append(f"previous run {data['previous_run']}")
    if data.get("closed"):
        facts.append("the report is closed; nothing was reopened")
    return {
        "role": "person",
        "title": "Reported again" if reopened else "Reporter replied",
        "body": str(data.get("text") or ""),
        "facts": facts,
        "tone": "warn" if reopened else "",
    }


def _specialist_reviewed(event: Event, task: Task) -> Fields:
    data = event.data
    area = str(data.get("area") or "specialist")
    allow = bool(data.get("allow"))
    concerns = [str(item) for item in data.get("concerns") or []]
    return {
        "role": "verifier",
        "title": f"{area.capitalize()} review {'allowed' if allow else 'blocked'}",
        "body": str(data.get("reason") or "No reason recorded."),
        "facts": [f"{len(concerns)} concern(s)", f"model {data.get('model') or '-'}"],
        "tone": "ok" if allow else "bad",
    }


def _wait(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "system",
        "title": {
            "wait.started": "Waiting",
            "wait.woken": "Woke up",
            "wait.expired": "Wait expired",
        }[event.type],
        "body": str(data.get("wake_on") or data.get("on") or ""),
    }


def _memory(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "system",
        "title": {
            "memory.reported": "PPMA synced",
            "memory.failed": "PPMA failed",
            "memory.recalled": "Memory recall",
            "memory.recall_failed": "Memory recall failed",
        }.get(event.type, "Memory"),
        "body": str(data.get("error") or data.get("via") or ""),
        "facts": [f"{len(data.get('statements') or [])} statement(s)"],
        "tone": "bad" if event.type.endswith("failed") else "",
    }
