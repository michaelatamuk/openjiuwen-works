"""Tiny event lookups shared by the presenters."""

from __future__ import annotations

from works.domain.records import Event


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
