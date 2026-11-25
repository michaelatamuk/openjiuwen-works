"""A rolling hash over a run's events: removing or editing one breaks the chain."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from works.domain.event import Event


def event_root(events: Iterable[Event]) -> str:
    previous = ""
    for event in sorted(events, key=lambda item: item.seq):
        payload = json.dumps(
            {
                "seq": event.seq,
                "ts": event.ts.isoformat(),
                "type": event.type,
                "data": event.data,
                "previous": previous,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
        previous = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return previous
