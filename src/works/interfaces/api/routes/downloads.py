"""Export and runtime-artifact downloads."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from works.interfaces.api import downloads
from works.interfaces.api.wiring import AppState

router = APIRouter()


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.works
    return state


def _respond(found: downloads.Download) -> Response:
    disposition = "inline" if found.inline else "attachment"
    return Response(
        content=found.body,
        media_type=found.content_type,
        headers={"Content-Disposition": f'{disposition}; filename="{found.filename}"'},
    )


@router.get("/tasks/{task_id}/export/{kind}")
def export(task_id: str, kind: str, request: Request) -> Response:
    found = downloads.find_export(_state(request).paths, task_id, kind)
    if found is None:
        raise HTTPException(404, detail="export not found")
    return _respond(found)


@router.get("/tasks/{task_id}/artifacts/{name:path}")
def artifact(task_id: str, name: str, request: Request) -> Response:
    found = downloads.find_artifact(_state(request).paths, task_id, name)
    if found is None:
        raise HTTPException(404, detail="artifact not found")
    return _respond(found)
