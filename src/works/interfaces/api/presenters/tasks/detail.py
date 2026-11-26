"""Task summaries and the full task detail."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from works.adapters.queue.files import INDEX_FILE
from works.adapters.queue.index import TaskIndex
from works.adapters.queue.store import Queue
from works.application.planning.store import PlanStore
from works.config.paths import WorksPaths
from works.domain.evidence import Evidence, render_summary
from works.domain.records import Event, Task
from works.interfaces.api.presenters.story import _pipeline
from works.interfaces.api.presenters.tasks.artifacts import _artifact_list
from works.interfaces.api.presenters.tasks.files import (
    _latest,
    _read_json,
    _run_index,
    feature_map,
    readiness,
)
from works.interfaces.api.presenters.thread import _thread, _thread_rail


def _task_summary(task: Task, events: list[Event]) -> dict[str, Any]:
    risk = _latest(events, "risk.rated")
    decision = _latest(events, "decision.made")
    would = [event for event in events if event.type == "would_block"]
    return {
        "id": task.id,
        "state": task.state.value,
        "flow": task.flow,
        "product": task.product,
        "source": f"{task.source.kind.value}:{task.source.ref}",
        "title": task.source.title,
        "kind": task.kind.value,
        "updated_at": task.updated_at.isoformat(),
        "risk": risk.data.get("level") if risk is not None else None,
        "decision": decision.data.get("verb") if decision is not None else None,
        "would_block": len(would),
        "waiting_on": task.waiting_on,
    }


def _run_summaries(paths: WorksPaths, task_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not paths.runs.exists():
        return items
    for run_json in paths.runs.glob("*/run.json"):
        data = _read_json(run_json)
        if not isinstance(data, dict) or data.get("task_id") != task_id:
            continue
        run_dir = run_json.parent
        evidence = _read_json(run_dir / "evidence.json") or {}
        delivery = _read_json(run_dir / "delivery.json")
        confirmation = _read_json(run_dir / "confirmation.json")
        verdict = evidence.get("verdict") or {}
        risk = evidence.get("risk") or {}
        items.append(
            {
                "run_id": str(data.get("run_id") or run_dir.name),
                "state": str(data.get("state") or ""),
                "finished_at": str(data.get("finished_at") or ""),
                "base_commit": str(data.get("base_commit") or ""),
                "proof_sha256": str(evidence.get("proof_sha256") or ""),
                "verdict": "allow" if verdict.get("allow") else "block" if verdict else "—",
                "risk": str(risk.get("level") or "—"),
                "tokens": int(data.get("tokens") or 0),
                "usd": float(data.get("usd") or 0.0),
                "duration_ms": int(data.get("duration_ms") or 0),
                "files": list(evidence.get("files_changed") or []),
                "not_tested": list(evidence.get("not_tested") or []),
                "delivered": bool(delivery),
                "confirmed": bool(confirmation and confirmation.get("ok")),
            }
        )
    items.sort(key=lambda item: item["finished_at"])
    return items


def _proof_summary(evidence: dict[str, object] | None) -> dict[str, str | bool]:
    """The stored summary, or one derived on read for records that predate it."""
    if not evidence:
        return {"text": "", "sha256": "", "derived": False}
    stored = str(evidence.get("summary") or "")
    derived = not stored
    text = stored
    if derived:
        try:
            text = render_summary(Evidence.model_validate(evidence))
        except ValidationError:
            text = ""
    return {
        "text": text,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "",
        "derived": derived,
    }


def _task_detail(
    queue: Queue, paths: WorksPaths, task_id: str, *, api_prefix: str = "/api"
) -> dict[str, Any]:
    task = queue.load(task_id)
    events = queue.events(task_id)
    runs = _run_index(paths)
    run_info = runs.get(task_id)
    run: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    proof_md = ""
    run_dir: Path | None = None
    if run_info is not None:
        run_dir = run_info[1]
        run = _read_json(run_dir / "run.json")
        evidence = _read_json(run_dir / "evidence.json")
        proof_path = run_dir / "evidence.md"
        if proof_path.exists():
            proof_md = proof_path.read_text(encoding="utf-8")
    timeline = [
        {
            "seq": event.seq,
            "ts": event.ts.isoformat(),
            "type": event.type,
            "data": event.data,
        }
        for event in events[-60:]
    ]
    from works.application.delivery.release import release_packet

    try:
        release = release_packet(paths, task_id).as_dict()
    except Exception as exc:  # a broken packet is shown as a blocker, not a 500
        release = {"ready": False, "released": False, "blockers": [str(exc)]}
    delivery = _read_json(run_dir / "delivery.json") if run_dir is not None else None
    deployment = _read_json(run_dir / "deployment.json") if run_dir is not None else None
    confirmation = _read_json(run_dir / "confirmation.json") if run_dir is not None else None
    from works.domain.errors import NotFoundError

    plan_payload: dict[str, Any] | None = None
    plan_diff: str | None = None
    try:
        store = PlanStore(paths)
        plan_payload = store.load(task_id).model_dump(mode="json")
        plan_diff = store.diff(task_id)
    except NotFoundError:
        plan_payload = None
    confirmations = [event.data for event in events if event.type == "confirmation.finished"][-5:]
    team_events = [event.data for event in events if event.type == "team.verified"]
    laix = [event.data for event in events if event.type == "decision.shadow"][-10:]
    verifier = {
        "name": str((evidence or {}).get("verifier") or (run or {}).get("verifier") or "local"),
        "isolation": str(
            (evidence or {}).get("verifier_isolation")
            or (run or {}).get("verifier_isolation")
            or "process"
        ),
    }
    team_payload = {
        "latest": team_events[-1] if team_events else None,
        "history": team_events[-10:],
    }
    replies = [event.data for event in events if event.type == "reporter.replied"]
    return {
        "task": task.model_dump(mode="json"),
        "summary": _task_summary(task, events),
        "run": run,
        "evidence": evidence,
        "proof_md": proof_md,
        "proof_summary": _proof_summary(evidence),
        "timeline": timeline,
        "pipeline": _pipeline(task, events, evidence, delivery, confirmation),
        "plan": plan_payload,
        "plan_diff": plan_diff,
        "confirmations": confirmations,
        "readiness": readiness(Path(task.repo)),
        "features": feature_map(Path(task.repo), evidence),
        "release": release,
        "delivery": delivery,
        "deployment": deployment,
        "confirmation": confirmation,
        "team": team_payload,
        "reporter": {"replies": len(replies), "last": replies[-1] if replies else None},
        "laix": laix,
        "verifier": verifier,
        "artifacts": _artifact_list(run_dir, task_id, evidence, prefix=api_prefix),
        "runs": _run_summaries(paths, task_id),
        "thread": _thread(task, events),
        "rail": _thread_rail(
            task, events, run, evidence, release, delivery, confirmation, team_payload, verifier
        ),
    }


def _iso_timestamp(value: object) -> str:
    text = str(value or "")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return text


def _index_summary(row: dict[str, Any], events: list[Event]) -> dict[str, Any]:
    risk = _latest(events, "risk.rated")
    decision = _latest(events, "decision.made")
    would = [event for event in events if event.type == "would_block"]
    source = row.get("source") or {}
    return {
        "id": row["id"],
        "state": row["state"],
        "flow": row["flow"],
        "product": row.get("product", ""),
        "source": f"{source.get('kind', '')}:{source.get('ref', '')}",
        "title": row.get("title", ""),
        "kind": row.get("kind", "fix"),
        "updated_at": _iso_timestamp(row.get("updated_at")),
        "risk": risk.data.get("level") if risk is not None else None,
        "decision": decision.data.get("verb") if decision is not None else None,
        "would_block": len(would),
        "waiting_on": row.get("waiting_on"),
    }


def _tasks(queue: Queue, limit: int) -> list[dict[str, Any]]:
    index_path = queue.paths.queue / INDEX_FILE
    if index_path.is_file():
        try:
            rows = TaskIndex(index_path).list_recent(limit)
        except sqlite3.DatabaseError:
            rows = []
        if rows:
            return [
                _index_summary(
                    row,
                    queue.events(row["id"]) if queue.exists(row["id"]) else [],
                )
                for row in rows
            ]
    tasks = queue.list_tasks()
    items = [_task_summary(task, queue.events(task.id)) for task in tasks]
    items.sort(key=lambda item: str(item["updated_at"]), reverse=True)
    return items[:limit]
