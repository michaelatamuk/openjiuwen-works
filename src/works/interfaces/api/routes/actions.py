"""Actions: short calls answer directly, long ones run as jobs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from works.domain.errors import ConfigError
from works.interfaces.api.jobs import JobContext
from works.interfaces.api.security import require_write
from works.interfaces.api.wiring import AppState

router = APIRouter()

SYNC = frozenset({"add-context", "approve-plan", "release"})
JOBS = frozenset({"commentary", "discussion", "deliver", "confirm", "team-verify", "deploy"})


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.works
    return state


def _task_id(payload: dict[str, Any]) -> str:
    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise ConfigError("task_id is required")
    return task_id


def _run_sync(state: AppState, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    task_id = _task_id(payload)
    if action == "add-context":
        message = str(payload.get("message") or "").strip()
        if not message:
            raise ConfigError("message is required")
        if len(message) > 2000:
            raise ConfigError("message is too long")
        with state.write_lock:
            event = state.queue.append(task_id, "thread.note", {"message": message, "by": "person"})
        return {"ok": True, "action": action, "event": event.model_dump(mode="json")}
    if action == "approve-plan":
        from works.application.approvals.gates import decide_plan

        decision = str(payload.get("decision") or "approved")
        with state.write_lock:
            task, event = decide_plan(
                state.paths,
                task_id,
                decision=decision,
                by=str(payload.get("by") or "ui"),
                device=str(payload.get("device") or "local"),
                comment=str(payload.get("comment") or ""),
            )
        return {
            "ok": True,
            "action": action,
            "decision": decision,
            "task": task.model_dump(mode="json"),
            "event": event.model_dump(mode="json"),
        }
    from works.application.delivery.release import decide_release

    decision = str(payload.get("decision") or "approved")
    with state.write_lock:
        task, packet, created = decide_release(
            state.paths,
            task_id,
            decision=decision,
            by=str(payload.get("by") or "ui"),
            device=str(payload.get("device") or "local"),
            comment=str(payload.get("comment") or ""),
        )
    return {
        "ok": True,
        "action": action,
        "decision": decision,
        "created": created,
        "task": task.model_dump(mode="json"),
        "release": packet.as_dict(),
    }


def _run_job(state: AppState, action: str, payload: dict[str, Any]) -> Any:
    task_id = _task_id(payload)
    if action == "commentary":
        from works.application.assistant.chat import generate_commentary

        return generate_commentary(state.paths, task_id)
    if action == "discussion":
        from works.application.assistant.chat import generate_discussion

        return generate_discussion(state.paths, task_id)
    if action == "deliver":
        from works.application.delivery.deliver import deliver

        delivery = deliver(
            state.paths,
            task_id,
            provider=str(payload.get("provider") or "none"),
            tracker=payload.get("tracker") or None,
            dry_run=bool(payload.get("dry_run")),
        )
        return delivery.as_dict()
    if action == "confirm":
        from works.application.delivery.confirm import confirm

        result = confirm(
            state.paths,
            task_id,
            url=str(payload.get("url") or "").strip() or None,
            command=payload.get("command"),
            tracker=payload.get("tracker") or None,
            close_issue=bool(payload.get("close")),
            force=bool(payload.get("force")),
        )
        return {"ok": result.ok, "confirmation": result.as_dict()}
    if action == "team-verify":
        from works.application.team.launcher import run_team_verify

        return run_team_verify(state.paths, task_id)
    from works.application.delivery.deploy import deploy

    deployment = deploy(
        state.paths,
        task_id,
        command=payload.get("command"),
        environment=str(payload.get("environment") or "staging"),
        dry_run=bool(payload.get("dry_run")),
        force=bool(payload.get("force")),
    )
    return deployment.as_dict()


def _job_body(state: AppState, action: str, payload: dict[str, Any]) -> Callable[[JobContext], Any]:
    def run(ctx: JobContext) -> Any:
        ctx.check()
        with state.write_lock:
            result = _run_job(state, action, payload)
        ctx.check()
        return result

    return run


@router.post("/actions", dependencies=[Depends(require_write)])
def run_action(request: Request, payload: dict[str, Any]) -> Any:
    state = _state(request)
    action = str(payload.get("action") or "").strip()
    if not action:
        raise ConfigError("action is required")
    if action in SYNC:
        return _run_sync(state, action, payload)
    if action == "ask":
        raise ConfigError("use POST /api/v1/ask/stream for questions")
    if action in JOBS:
        task_id = _task_id(payload)
        job = state.jobs.submit(action, _job_body(state, action, payload), task_id=task_id)
        return JSONResponse(
            status_code=202,
            content={"ok": True, "action": action, "job": job.as_dict()},
        )
    raise ConfigError(f"unknown action {action!r}")
