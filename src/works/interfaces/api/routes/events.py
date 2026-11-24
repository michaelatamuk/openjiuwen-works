"""Named live events over server-sent events."""

from __future__ import annotations

import json
import queue as thread_queue
import time
from collections.abc import Iterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from works.interfaces.api.live import SseEvent
from works.interfaces.api.wiring import AppState

router = APIRouter()
HEARTBEAT_SECONDS = 15


def _format(item: SseEvent) -> str:
    data = json.dumps(item.data, ensure_ascii=False, default=str)
    return f"id: {item.id}\nevent: {item.event}\ndata: {data}\n\n"


def _heartbeat() -> str:
    return f"event: heartbeat\ndata: {json.dumps({'ts': time.time()})}\n\n"


@router.get("/events")
def events(request: Request) -> StreamingResponse:
    state: AppState = request.app.state.works
    hub = state.live
    raw = request.headers.get("last-event-id")
    try:
        last_id = int(raw) if raw else None
    except ValueError:
        last_id = None
    channel = hub.subscribe()
    missed, gap = hub.events_after(last_id)

    def generate() -> Iterator[str]:
        try:
            yield ": connected\n\n"
            if gap:
                resync = SseEvent(hub.counter, "resync", {"epoch": hub.epoch, "reason": "gap"})
                yield _format(resync)
            for item in missed:
                yield _format(item)
            while True:
                try:
                    item = channel.get(timeout=HEARTBEAT_SECONDS)
                except thread_queue.Empty:
                    yield _heartbeat()
                else:
                    yield _format(item)
        finally:
            hub.unsubscribe(channel)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
