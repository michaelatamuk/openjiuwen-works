"""Streamed Ask Mira answers."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from works.domain.errors import ConfigError
from works.interfaces.api.security import require_write
from works.interfaces.api.wiring import AppState

router = APIRouter()


@router.post("/ask/stream", dependencies=[Depends(require_write)])
def ask_stream(request: Request, payload: dict[str, Any]) -> StreamingResponse:
    state: AppState = request.app.state.works
    task_id = str(payload.get("task_id") or "").strip()
    question = str(payload.get("question") or "").strip()
    if not task_id or not question:
        raise ConfigError("task_id and question are required")
    state.queue.load(task_id)

    def generate() -> Iterator[str]:
        try:
            from works.application.assistant.chat import ask_mira_stream

            for event in ask_mira_stream(state.paths, task_id, question):
                body = json.dumps(event, ensure_ascii=False, default=str)
                yield f"data: {body}\n\n"
        except Exception as exc:  # after headers, an error is an SSE event
            body = json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False)
            yield f"data: {body}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
