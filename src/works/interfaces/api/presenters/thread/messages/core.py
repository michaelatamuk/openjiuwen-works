"""The dispatcher: one small handler per event kind, grouped by lifecycle stage."""

from __future__ import annotations

from typing import Any

from works.domain.records import Event, Task
from works.interfaces.api.presenters.thread.messages.build import (
    _attempt_started,
    _challenge_decided,
    _decision_made,
    _finding,
    _flake,
    _risk_rated,
    _shadow,
    _step_finished,
    _would_block,
)
from works.interfaces.api.presenters.thread.messages.deliver import (
    _confirmation_finished,
    _delivery_finished,
    _deploy_finished,
    _escape,
    _rework,
)
from works.interfaces.api.presenters.thread.messages.notes import (
    _agent,
    _commentary,
    _discussion,
    _memory,
    _note,
    _reporter_replied,
    _specialist_reviewed,
    _thread_note,
    _wait,
)
from works.interfaces.api.presenters.thread.messages.plan import (
    _gate_decided,
    _plan_deviation,
    _plan_drafted,
)
from works.interfaces.api.presenters.thread.messages.signal import _created
from works.interfaces.api.presenters.thread.messages.types import Fields, Handler
from works.interfaces.api.presenters.thread.messages.verify import (
    _preview,
    _readiness,
    _state_changed,
    _team_verified,
)

_HANDLERS: dict[str, Handler] = {
    "task.created": _created,
    "plan.drafted": _plan_drafted,
    "plan.deviation": _plan_deviation,
    "gate.decided": _gate_decided,
    "attempt.started": _attempt_started,
    "step.finished": _step_finished,
    "challenge.decided": _challenge_decided,
    "risk.rated": _risk_rated,
    "decision.made": _decision_made,
    "decision.shadow": _shadow,
    "finding": _finding,
    "flake": _flake,
    "would_block": _would_block,
    "readiness.checked": _readiness,
    "team.verified": _team_verified,
    "delivery.finished": _delivery_finished,
    "confirmation.finished": _confirmation_finished,
    "deploy.finished": _deploy_finished,
    "escape.detected": _escape,
    "rework.detected": _rework,
    "thread.agent": _agent,
    "thread.commentary": _commentary,
    "thread.discussion": _discussion,
    "thread.note": _thread_note,
    "reporter.replied": _reporter_replied,
    "specialist.reviewed": _specialist_reviewed,
    "note": _note,
    "wait.started": _wait,
    "wait.woken": _wait,
    "wait.expired": _wait,
    "state.changed": _state_changed,
    "preview.finished": _preview,
}
_PREFIX_HANDLERS: tuple[tuple[str, Handler], ...] = (("memory.", _memory),)


def _thread_message(event: Event, task: Task) -> dict[str, Any] | None:
    handler = _HANDLERS.get(event.type)
    if handler is None:
        for prefix, candidate in _PREFIX_HANDLERS:
            if event.type.startswith(prefix):
                handler = candidate
                break
    if handler is None:
        return None
    fields = handler(event, task)
    if fields is None:
        return None
    return _message(event, fields)


def _message(event: Event, fields: Fields) -> dict[str, Any]:
    return {
        "seq": event.seq,
        "at": event.ts.isoformat(),
        "role": fields.get("role", "system"),
        "type": event.type,
        "title": fields.get("title", event.type),
        "body": fields.get("body", ""),
        "facts": [item for item in (fields.get("facts") or []) if item],
        "tone": fields.get("tone", ""),
        "generated": bool(event.data.get("generated")) or bool(fields.get("generated")),
        "generated_label": fields.get("generated_label", ""),
        "stance": fields.get("stance", ""),
        "card": fields.get("card"),
    }
