"""HTTP API presenters and runtime helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from works.adapters.queue.store import Queue
from works.application.intake.detectors import alerts_for, load_config
from works.application.intake.products import MAP_PATH, load_products
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError
from works.domain.records import Event, Task
from works.interfaces.api.presenters.story import _pipeline
from works.interfaces.api.presenters.thread import _thread, _thread_rail


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _latest(events: list[Event], kind: str) -> Event | None:
    found: Event | None = None
    for event in events:
        if event.type == kind:
            found = event
    return found


def _run_index(paths: WorksPaths) -> dict[str, tuple[str, Path]]:
    """Map task id to its newest run directory."""
    index: dict[str, tuple[str, Path]] = {}
    if not paths.runs.exists():
        return index
    for run_json in paths.runs.glob("*/run.json"):
        data = _read_json(run_json)
        if not isinstance(data, dict):
            continue
        task_id = data.get("task_id")
        finished = str(data.get("finished_at", ""))
        if not isinstance(task_id, str):
            continue
        previous = index.get(task_id)
        if previous is None or finished >= previous[0]:
            index[task_id] = (finished, run_json.parent)
    return index


def readiness(repo: Path) -> dict[str, Any]:
    from works.application.execution.readiness import assess

    return assess(repo, run_commands=False).as_dict()


def feature_map(repo: Path, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    from works.application.observability.features import feature_summary

    return feature_summary(repo, evidence)


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


def product_map(paths: WorksPaths) -> dict[str, Any]:
    mapping = load_products(paths)
    items: list[dict[str, Any]] = []
    for name, entry in sorted(mapping.products.items()):
        repo = Path(entry.repo).expanduser()
        if not repo.is_absolute():
            repo = paths.root / repo
        repo = repo.resolve()
        items.append(
            {
                "name": name,
                "repo": str(repo),
                "exists": repo.is_dir(),
                "git": (repo / ".git").exists(),
            }
        )
    return {
        "path": MAP_PATH.as_posix(),
        "configured": bool(items),
        "products": items,
    }


def detector_map(paths: WorksPaths, *, refresh: bool = False) -> dict[str, Any]:
    config = load_config(paths)
    items: list[dict[str, Any]] = []
    for name, source in sorted(config.detectors.items()):
        alerts: list[dict[str, Any]] = []
        error: str | None = None
        if source.file or refresh:
            try:
                alerts = [
                    {
                        "ref": alert.ref,
                        "title": alert.title,
                        "severity": alert.severity,
                        "status": alert.status,
                    }
                    for alert in alerts_for(paths, name)
                ]
            except ConfigError as exc:
                error = str(exc)
        items.append(
            {
                "name": name,
                "product": source.product,
                "file": source.file,
                "url": source.url,
                "alerts": alerts,
                "error": error,
                "needs_refresh": bool(source.url and not refresh),
            }
        )
    return {"path": ".works/detectors.yaml", "configured": bool(items), "detectors": items}


def _artifact_kind(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}:
        return "image"
    if suffix in {".mp4", ".webm", ".mov"}:
        return "video"
    if suffix in {".log", ".txt", ".md"}:
        return "log"
    if suffix in {".json", ".trace"}:
        return "trace"
    return "file"


def _artifact_list(
    run_dir: Path | None, task_id: str, evidence: dict[str, Any] | None
) -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for artifact in (evidence or {}).get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        relative = str(artifact.get("path") or "").removeprefix("artifacts/")
        if not relative:
            continue
        items[relative] = {
            "path": relative,
            "name": Path(relative).name,
            "kind": str(artifact.get("kind") or _artifact_kind(relative)),
            "sha256": str(artifact.get("sha256") or ""),
            "url": f"/api/tasks/{quote(task_id)}/artifacts/"
            + "/".join(quote(part) for part in relative.split("/")),
        }
    root = (run_dir / "artifacts") if run_dir is not None else None
    if root is not None and root.exists():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if relative in items:
                continue
            items[relative] = {
                "path": relative,
                "name": path.name,
                "kind": _artifact_kind(relative),
                "sha256": "",
                "size": path.stat().st_size,
                "url": f"/api/tasks/{quote(task_id)}/artifacts/"
                + "/".join(quote(part) for part in relative.split("/")),
            }
    return sorted(items.values(), key=lambda item: item["path"])


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


def _export(paths: WorksPaths, task_id: str, kind: str) -> tuple[Path, str] | None:
    run_info = _run_index(paths).get(task_id)
    if run_info is None:
        return None
    run_dir = run_info[1]
    names = {
        "evidence.md": run_dir / "evidence.md",
        "evidence.json": run_dir / "evidence.json",
        "run.json": run_dir / "run.json",
        "release.json": run_dir / "release.json",
        "delivery.json": run_dir / "delivery.json",
        "deployment.json": run_dir / "deployment.json",
        "confirmation.json": run_dir / "confirmation.json",
    }
    target = names.get(kind)
    if target is None or not target.is_file():
        return None
    return target, f"{task_id}-{kind}"


def _task_detail(queue: Queue, paths: WorksPaths, task_id: str) -> dict[str, Any]:
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
    return {
        "task": task.model_dump(mode="json"),
        "summary": _task_summary(task, events),
        "run": run,
        "evidence": evidence,
        "proof_md": proof_md,
        "timeline": timeline,
        "pipeline": _pipeline(task, events, evidence, delivery, confirmation),
        "readiness": readiness(Path(task.repo)),
        "features": feature_map(Path(task.repo), evidence),
        "release": release,
        "delivery": delivery,
        "deployment": deployment,
        "confirmation": confirmation,
        "team": team_payload,
        "laix": laix,
        "verifier": verifier,
        "artifacts": _artifact_list(run_dir, task_id, evidence),
        "runs": _run_summaries(paths, task_id),
        "thread": _thread(task, events),
        "rail": _thread_rail(
            task, events, run, evidence, release, delivery, confirmation, team_payload, verifier
        ),
    }


def _tasks(queue: Queue, limit: int) -> list[dict[str, Any]]:
    tasks = queue.list_tasks()
    items = [_task_summary(task, queue.events(task.id)) for task in tasks]
    items.sort(key=lambda item: str(item["updated_at"]), reverse=True)
    return items[:limit]
