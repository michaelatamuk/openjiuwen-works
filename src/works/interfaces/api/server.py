"""A read-only preview of the factory: queue, task, proof, risk and decisions."""

from __future__ import annotations

import json
import logging
import queue as thread_queue
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, quote, unquote, urlparse

from works.adapters.queue.ledger import Ledger
from works.adapters.queue.store import Queue
from works.application.intake.detectors import alerts_for, ingest_named, load_config
from works.application.intake.products import MAP_PATH, load_products, resolve_repo
from works.application.observability.metrics import collect
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError
from works.domain.records import Event, Source, SourceKind, Task, TaskKind

LOG = logging.getLogger("works.ui")
STATIC = {
    "": "index.html",
    "index.html": "index.html",
    "app.css": "app.css",
    "app.js": "app.js",
    "mira.svg": "mira.svg",
}
ASSETS = Path(__file__).resolve().parents[1] / "ui" / "static"
DIST = ASSETS / "dist"


class LiveState:
    """Watch the workspace on disk and wake every open browser when it changes."""

    def __init__(self, paths: WorksPaths, *, interval: float = 0.6) -> None:
        self._paths = paths
        self._interval = interval
        self._subscribers: set[thread_queue.Queue[dict[str, Any]]] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._signature: tuple[tuple[str, int, int], ...] | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._signature = self._snapshot()
        self._thread = threading.Thread(target=self._loop, name="works-ui-events", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        self._thread = None

    def subscribe(self) -> thread_queue.Queue[dict[str, Any]]:
        channel: thread_queue.Queue[dict[str, Any]] = thread_queue.Queue(maxsize=64)
        with self._lock:
            self._subscribers.add(channel)
        return channel

    def unsubscribe(self, channel: thread_queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers.discard(channel)

    def _snapshot(self) -> tuple[tuple[str, int, int], ...]:
        files = [self._paths.ledger]
        files.extend(self._paths.queue.glob("*/events.jsonl"))
        files.extend(self._paths.queue.glob("*/task.json"))
        files.extend(self._paths.runs.glob("*/*.json"))
        files.extend(self._paths.runs.glob("*/artifacts/*"))
        parts: list[tuple[str, int, int]] = []
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            parts.append((str(path), stat.st_mtime_ns, stat.st_size))
        return tuple(parts)

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            signature = self._snapshot()
            if signature == self._signature:
                continue
            self._signature = signature
            payload = {"type": "changed", "at": time.time()}
            with self._lock:
                subscribers = list(self._subscribers)
            for channel in subscribers:
                try:
                    channel.put_nowait(payload)
                except thread_queue.Full:
                    continue


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


def _pipeline(
    task: Task,
    events: list[Event],
    evidence: dict[str, Any] | None,
    delivery: dict[str, Any] | None = None,
    confirmation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A story line and a technical line, both derived from events and evidence."""
    state = task.state.value
    stop = str((evidence or {}).get("stop_reason", ""))
    current = {
        "queued": 0,
        "reproducing": 1,
        "reproduced": 2,
        "planning": 2,
        "plan_approved": 4,
        "building": 4,
        "checking": 5,
        "proved": 7,
        "releasing": 7,
        "released": 8,
    }.get(state, 0)
    if confirmation is not None:
        current = 10
    elif delivery is not None:
        current = 9
    if state == "blocked":
        current = {
            "not_reproducible": 1,
            "policy_violation": 5,
            "tests_failed": 5,
            "flaky_test": 5,
            "budget_exceeded": 5,
            "challenge_failed": 6,
            "verdict_failed": 6,
            "harness_failed": 4,
            "config_error": 4,
            "conflict": 4,
        }.get(stop, 5)

    specs = [
        ("signal", "Read the signal", "source"),
        ("reproduce", "Reproduce", "agent"),
        ("plan", "Plan", "agent"),
        ("plan_gate", "Plan approved", "gate"),
        ("build", "Build", "agent"),
        ("check", "Check", "verify"),
        ("proof", "Proof", "artifact"),
        ("release_gate", "Release approved", "gate"),
        ("deliver", "Deliver", "source"),
        ("confirm", "Confirm", "verify"),
    ]
    plan = next((event.data for event in reversed(events) if event.type == "plan.drafted"), {})
    files = (evidence or {}).get("files_changed") or []
    verdict = (evidence or {}).get("verdict") or {}
    challenge = (evidence or {}).get("challenge") or {}
    risk = (evidence or {}).get("risk") or {}
    gate_plan = _first(events, "gate.decided")
    gate_release = next(
        (
            event
            for event in reversed(events)
            if event.type == "gate.decided" and event.data.get("gate") == "release"
        ),
        None,
    )

    def stage_state(index: int) -> str:
        if state == "blocked" and index == current:
            return "blocked"
        if index < current:
            return "done"
        if index == current:
            return "active"
        return "pending"

    def artifacts(index: int) -> list[str]:
        if index == 0:
            return [f"{task.source.kind.value}:{task.source.ref}", task.source.title]
        if index == 1:
            command = (evidence or {}).get("reproduce") or {}
            return [
                f"exit {command.get('exit_code', '?')}",
                "the problem was reproduced" if command else "not run",
            ]
        if index == 2:
            ids = plan.get("scenario_ids") or []
            return [f"{len(ids)} scenario(s)", "plan drafted"]
        if index == 3:
            if gate_plan is None:
                return ["waiting for a person"]
            return [
                f"by {gate_plan.data.get('by', '?')}",
                f"commit {str(gate_plan.data.get('commit', '?'))[:10]}",
            ]
        if index == 4:
            return [f"{len(files)} file(s) changed", f"model {(evidence or {}).get('model', '—')}"]
        if index == 5:
            return [
                f"verdict {'allow' if verdict.get('allow') else 'block'}",
                f"challenge {'allow' if challenge.get('allow') else 'block'}"
                if challenge
                else "no challenge",
            ]
        if index == 6:
            return [
                f"risk {risk.get('level', '—')}",
                f"proof {str((evidence or {}).get('proof_sha256', ''))[:10]}",
            ]
        if index == 7:
            if gate_release is None:
                return ["waiting for a person" if state == "proved" else "not reached"]
            return [
                f"by {gate_release.data.get('by', '?')}",
                f"commit {str(gate_release.data.get('commit', '?'))[:10]}",
            ]
        if index == 8:
            if delivery is None:
                return ["not delivered" if state == "released" else "not reached"]
            return [
                f"branch {delivery.get('branch', '?')!s}",
                f"commit {str(delivery.get('commit', '?'))[:10]}",
            ]
        if confirmation is None:
            return ["awaiting confirmation"]
        return [
            f"confirmation {'pass' if confirmation.get('ok') else 'fail'}",
            str(confirmation.get("target", "—")),
        ]

    at = [
        _first_at(events, "task.created"),
        _first_at(events, "step.finished", step="reproduce"),
        _first_at(events, "plan.drafted"),
        gate_plan.ts.isoformat() if gate_plan is not None else None,
        _first_at(events, "attempt.started"),
        _first_at(events, "step.finished", step="test")
        or _first_at(events, "step.started", step="test")
        or _first_at(events, "step.started", step="check"),
        next((event.ts.isoformat() for event in reversed(events) if event.type == "note"), None),
        gate_release.ts.isoformat() if gate_release is not None else None,
        next(
            (
                event.ts.isoformat()
                for event in events
                if event.type == "state.changed" and event.data.get("to") == "released"
            ),
            None,
        ),
        next(
            (
                event.ts.isoformat()
                for event in reversed(events)
                if event.type == "delivery.finished"
            ),
            None,
        ),
        next(
            (
                event.ts.isoformat()
                for event in reversed(events)
                if event.type == "confirmation.finished"
            ),
            None,
        ),
    ]
    technical: list[dict[str, Any]] = [
        {
            "id": key,
            "label": label,
            "kind": kind,
            "state": stage_state(index),
            "at": at[index],
            "artifacts": artifacts(index),
        }
        for index, (key, label, kind) in enumerate(specs)
    ]

    story_specs = [
        ("reported", "Reported", [], "A person reported the problem."),
        ("picked_up", "Picked up", [0], "Mira picked it up."),
        ("confirmed", "Confirmed", [1], "We saw it happen."),
        ("fixed", "Fixed", [2, 3, 4], "We built a fix."),
        ("checked", "Checked", [5, 6], "We checked it."),
        ("delivered", "Delivered", [7, 8, 9], "The fix is on its way back."),
    ]
    blocked_why = {
        "not_reproducible": "The problem could not be reproduced, so no fix can be proven.",
        "policy_violation": "The change touched a protected area, so the factory stopped.",
        "tests_failed": "A test that must pass failed after the change.",
        "flaky_test": "A test passes only sometimes, so the result cannot be trusted yet.",
        "challenge_failed": "The independent reviewer found a problem the fix did not resolve.",
        "verdict_failed": "A must-pass check failed, so the fix is not safe to release.",
        "budget_exceeded": "The run hit its budget before the fix could be proven.",
        "harness_failed": "The builder could not produce a fix that passed the checks.",
    }.get(stop, "The factory stopped before the fix was proven.")
    blocked_next = (
        "A person needs to review the evidence and decide whether to retry or change the plan."
    )
    blocked_key = None
    if state == "blocked":
        blocked_key = next((key for key, _, indexes, _ in story_specs if current in indexes), None)
    pickup_at = (
        next(
            (
                event.ts.isoformat()
                for event in events
                if event.type == "state.changed" and event.data.get("to") == "reproducing"
            ),
            None,
        )
        or at[1]
    )

    story: list[dict[str, Any]] = []
    for key, label, indexes, caption in story_specs:
        states = [technical[index]["state"] for index in indexes]
        if key == "reported":
            stage = "done"
        elif key == "picked_up":
            stage = "done" if current > 0 else "pending"
        elif "blocked" in states:
            stage = "blocked"
        elif all(item == "done" for item in states):
            stage = "done"
        elif any(item == "active" for item in states):
            stage = "active"
        else:
            stage = "pending"
        if key == "delivered":
            if confirmation is not None:
                label = f"Confirmed in {task.product}"
                caption = (
                    f"The released fix was confirmed in {task.product}."
                    if confirmation.get("ok")
                    else f"The confirmation in {task.product} failed."
                )
            elif delivery is not None:
                label = f"Back in {task.product}"
                caption = f"The fix was delivered to {task.product}. Confirmation is next."
            else:
                label = (
                    f"Release to {task.product}"
                    if state == "proved"
                    else f"Deliver to {task.product}"
                )
                caption = (
                    f"The fix is ready to go back to {task.product}."
                    if state == "proved"
                    else f"The fix is released and ready to be delivered to {task.product}."
                    if state == "released"
                    else f"The fix is on its way back to {task.product}."
                )
        story_at = (
            at[0]
            if key == "reported"
            else pickup_at
            if key == "picked_up"
            else next((technical[index]["at"] for index in indexes if technical[index]["at"]), None)
        )
        if key == blocked_key:
            stage = "blocked"
            caption = "Stopped here"
            story_artifacts = ["The fix was not released"]
        elif key == "reported":
            source = {"manual": "a person", "tracker": "the tracker", "detector": "monitoring"}
            story_artifacts = [
                f"Reported through {source.get(task.source.kind.value, 'the source')}",
                task.source.title,
            ]
        elif key == "picked_up":
            story_artifacts = ["Mira took the report", f"Work started on {task.product}"]
        elif key == "confirmed":
            story_artifacts = [
                "The problem was reproduced",
                "Before the fix, the check failed",
            ]
        elif key == "fixed":
            story_artifacts = [
                "The plan was approved",
                f"{len(files)} file(s) changed",
                "The fix was built",
            ]
        elif key == "checked":
            story_artifacts = (
                [
                    "All must-pass checks passed",
                    "The independent review passed"
                    if challenge.get("allow")
                    else "The independent review found a concern",
                ]
                if verdict.get("allow")
                else [
                    "A must-pass check failed",
                    "The fix is not safe to release",
                ]
            )
        elif key == "delivered":
            if confirmation is not None:
                story_artifacts = [
                    "The released fix was confirmed"
                    if confirmation.get("ok")
                    else "The confirmation failed",
                    str(confirmation.get("target", "—")),
                ]
            elif delivery is not None:
                story_artifacts = [
                    f"Delivered on {delivery.get('branch', 'a branch')}",
                    str(
                        delivery.get("pr_url")
                        or delivery.get("comment_url")
                        or "back to the source"
                    ),
                ]
            else:
                story_artifacts = (
                    ["The fix is released and ready to deliver"]
                    if state == "released"
                    else ["The fix is ready to go back to the source"]
                    if state == "proved"
                    else ["Not delivered yet"]
                )
        else:
            story_artifacts = ["Not reached yet"]
        story.append(
            {
                "id": key,
                "label": label,
                "kind": "source"
                if key == "reported"
                else "gate"
                if key == "delivered"
                else "stage",
                "state": stage,
                "at": story_at,
                "caption": caption,
                "artifacts": story_artifacts,
            }
        )

    def event_stage(event: Event) -> str:
        if event.type == "task.created":
            return "signal"
        if event.type == "plan.drafted":
            return "plan"
        if event.type == "gate.decided":
            return "plan_gate" if event.data.get("gate") == "plan" else "release_gate"
        if event.type == "attempt.started":
            return "build"
        if event.type == "step.started":
            return {"reproduce": "reproduce", "test": "check", "build": "build"}.get(
                str(event.data.get("step")), "signal"
            )
        if event.type == "step.finished":
            step = event.data.get("step")
            return "reproduce" if step == "reproduce" else "check" if step == "test" else "build"
        if event.type == "challenge.decided":
            return "check"
        if event.type == "decision.made":
            gate = event.data.get("gate")
            return (
                "plan_gate" if gate == "plan" else "release_gate" if gate == "release" else "proof"
            )
        if event.type in ("risk.rated", "note"):
            return "proof"
        if event.type == "state.changed":
            target = str(event.data.get("to"))
            if target == "blocked":
                return {
                    "not_reproducible": "reproduce",
                    "harness_failed": "build",
                    "config_error": "build",
                    "conflict": "build",
                }.get(stop, "check")
            return {
                "queued": "signal",
                "reproducing": "reproduce",
                "reproduced": "reproduce",
                "planning": "plan",
                "plan_approved": "plan_gate",
                "building": "build",
                "checking": "check",
                "proved": "proof",
                "releasing": "release_gate",
                "released": "deliver",
                "reverted": "deliver",
            }.get(target, "confirm")
        return "signal"

    replay = [
        {
            "at": event.ts.isoformat(),
            "stage": event_stage(event),
            "type": event.type,
            "data": event.data,
        }
        for event in events[-200:]
    ]
    blocked = None
    if state == "blocked":
        failed = [str(item) for item in (verdict.get("p0_failed") or [])]
        check = failed[0].replace("-", " ") if failed else "one must-pass check"
        blocked = {
            "why": blocked_why,
            "next": blocked_next,
            "check": check,
            "impact": f"Nothing was released to {task.product}. The problem is still there.",
        }
    return {
        "story": story,
        "technical": technical,
        "replay": replay,
        "blocked": blocked,
    }


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


def _thread_message(event: Event, task: Task) -> dict[str, Any] | None:
    data = event.data
    kind = event.type
    role = "system"
    title = kind
    body = ""
    facts: list[str] = []
    tone = ""
    card: dict[str, Any] | None = None
    generated_label = ""
    generated = False
    stance = ""

    if kind == "task.created":
        role = {
            "manual": "person",
            "tracker": "tracker",
            "detector": "monitor",
        }.get(task.source.kind.value, "person")
        title = "Reported"
        body = task.source.title
        facts = [f"{task.source.kind.value}:{task.source.ref}", task.product]
    elif kind == "plan.drafted":
        role = "builder"
        title = "Plan drafted"
        summary = str(data.get("summary") or "A plan for the flow and its must-pass scenarios.")
        body = summary if len(summary) <= 280 else summary[:277].rstrip() + "..."
        ids = data.get("scenario_ids") or []
        p0 = data.get("p0") or []
        p1 = data.get("p1") or []
        provenance = data.get("provenance") or {}
        validation = data.get("validation") or {}
        nodes = data.get("nodes") or []
        plan_id = str(data.get("plan_id") or "unversioned")
        plan_hash = str(data.get("hash") or "")
        facts = [
            plan_id,
            f"{len(nodes)} step(s)",
            f"{len(ids)} scenario(s)",
            f"{len(p0)} P0",
            f"{len(p1)} P1",
        ]
        planner = str(provenance.get("planner") or "deterministic")
        model = provenance.get("model")
        rows = [
            ["Plan", plan_id],
            ["Steps", " -> ".join(nodes)],
            ["Scenarios", f"{len(ids)} ({len(p0)} P0 / {len(p1)} P1)"],
            ["Planner", f"{planner}" + (f" / {model}" if model else "")],
            ["Lint", "ok" if validation.get("ok") else "failed"],
        ]
        if plan_hash:
            rows.append(["Hash", plan_hash[:12]])
        tokens = int(provenance.get("tokens") or 0)
        usd = float(provenance.get("usd") or 0.0)
        rows.append(
            [
                "Planner cost",
                f"{tokens} tokens / ${usd:.4f}" if tokens else "not reported",
            ]
        )
        for warning in (validation.get("warnings") or [])[:3]:
            rows.append(["Warning", str(warning)])
        card = {
            "kind": "question",
            "prompt": "Review the plan, then approve it or open the run.",
            "rows": rows,
            "options": (
                [
                    {
                        "label": "Approve plan",
                        "action": "approve-plan",
                        "tone": "primary",
                        "recommended": True,
                    },
                    {"label": "Open run", "action": "open-run"},
                ]
                if task.state.value == "planning"
                else [{"label": "Open run", "action": "open-run"}]
            ),
        }
    elif kind == "plan.deviation":
        role = "system"
        title = "Plan drift"
        deviations = data.get("deviations") or []
        body = "The builder touched paths outside the plan's named write scope."
        facts = [f"plan {data.get('plan_id', '?')}", *[str(item) for item in deviations]]
        card = {
            "kind": "question",
            "prompt": "Visible drift is not a failure, but the proof now records it.",
            "rows": [["Unplanned", ", ".join(str(item) for item in deviations)]],
            "options": [{"label": "Open evidence", "action": "open-evidence"}],
        }
    elif kind == "gate.decided":
        role = "person"
        gate = str(data.get("gate") or "gate")
        title = "Plan approved" if gate == "plan" else "Release approved"
        body = f"{data.get('by', 'a person')} opened the {gate} gate."
        facts = [f"commit {str(data.get('commit', '—'))[:12]}"]
        if data.get("proof_sha256"):
            facts.append(f"proof {str(data['proof_sha256'])[:12]}")
        card = {
            "kind": "gate",
            "rows": [
                ["Gate", gate],
                ["Decision", str(data.get("decision", "approved"))],
                ["By", str(data.get("by", "—"))],
                ["Commit", str(data.get("commit", "—"))[:12]],
            ],
        }
        tone = "ok"
    elif kind == "attempt.started":
        role = "builder"
        title = f"Build attempt {data.get('attempt', '?')} started"
        body = "The builder is editing the disposable worktree."
    elif kind == "step.finished":
        step = str(data.get("step") or "step")
        code = data.get("exit_code", "?")
        role = "verifier" if step in ("reproduce", "test", "preview", "check") else "builder"
        if step == "reproduce":
            title = "Reproduction confirmed" if code != 0 else "Reproduction did not fail"
            body = (
                "The failing check failed on the base commit, as expected."
                if code != 0
                else "The check passed on the base commit, so the bug was not reproduced."
            )
            tone = "ok" if code != 0 else "bad"
        elif step == "test":
            title = "Tests passed" if code == 0 else "Tests failed"
            body = f"Exit code {code}."
            tone = "ok" if code == 0 else "bad"
        elif step == "preview":
            title = "Preview passed" if code == 0 else "Preview failed"
            body = f"Exit code {code}."
            tone = "ok" if code == 0 else "bad"
        else:
            title = f"{step.capitalize()} finished"
            body = f"Exit code {code}."
            tone = "ok" if code == 0 else "bad"
        facts = [step]
    elif kind == "challenge.decided":
        role = "challenger"
        allow = bool(data.get("allow"))
        title = "Independent check allowed" if allow else "Independent check blocked"
        body = str(data.get("reason") or "No reason recorded.")
        facts = [f"concerns {len(data.get('concerns') or [])}"]
        card = {
            "kind": "challenge",
            "rows": [["Allow", "yes" if allow else "no"], ["Model", str(data.get("model", "—"))]],
        }
        tone = "ok" if allow else "bad"
    elif kind == "risk.rated":
        role = "verifier"
        title = f"Risk: {data.get('level', 'unknown')}"
        body = (
            "; ".join(str(item) for item in (data.get("reasons") or [])) or "No reasons recorded."
        )
        facts = [f"owners {', '.join(data.get('owners') or []) or 'none'}"]
    elif kind == "decision.made":
        role = "verifier"
        title = f"Decision: {data.get('verb', '—')}"
        body = str(data.get("reason_code") or "")
        facts = [f"gate {data.get('gate', '—')}"]
    elif kind == "finding":
        role = "verifier"
        title = "Finding recorded"
        body = str(data.get("summary") or "")
        facts = [f"step {data.get('step', '—')}", f"confidence {data.get('confidence', '—')}"]
        tone = "bad"
    elif kind == "flake":
        role = "verifier"
        title = "Flaky test recorded"
        body = f"{data.get('scenario_id', '?')} has an owner and an expiry."
        facts = [f"owner {data.get('owner', '—')}"]
        tone = "bad"
    elif kind == "would_block":
        role = "verifier"
        title = "Observe mode would block"
        body = f"{data.get('gate', '—')}: {data.get('reason', '')}"
        tone = "bad"
    elif kind == "readiness.checked":
        role = "verifier"
        title = f"Readiness: {data.get('status', '—')}"
        body = f"{data.get('passed', '?')} of {data.get('total', '?')} checks passed."
        facts = [str(data.get("note") or "")]
        tone = "ok" if data.get("status") == "pass" else "bad"
    elif kind == "team.verified":
        role = "team"
        verdict = str(data.get("verdict") or "?")
        title = f"Team verdict: {verdict}"
        blockers = data.get("blockers") or []
        body = "; ".join(str(item) for item in blockers) or "No blockers."
        inspector = data.get("inspector") or {}
        challenger = data.get("challenger") or {}
        inspector_text = (
            ("allow" if inspector.get("allow") else "block") if inspector else "not recorded"
        )
        challenger_text = (
            ("allow" if challenger.get("allow") else "block") if challenger else "not recorded"
        )
        facts = [f"inspector {inspector_text}", f"challenger {challenger_text}"]
        card = {
            "kind": "team",
            "rows": [
                ["Verdict", verdict],
                ["Inspector", inspector_text],
                ["Challenger", challenger_text],
            ],
        }
        tone = "ok" if verdict == "allow" else "bad"
    elif kind == "delivery.finished":
        role = "delivery"
        title = "Delivered"
        body = f"{data.get('branch', '?')} · {str(data.get('commit', '?'))[:12]}"
        facts = [str(data.get("provider") or "none"), str(data.get("tracker") or "none")]
        card = {
            "kind": "delivery",
            "rows": [
                ["Branch", str(data.get("branch", "—"))],
                ["Commit", str(data.get("commit", "—"))[:12]],
                ["Pull request", str(data.get("pr_url") or "—")],
                ["Comment", str(data.get("comment_url") or "—")],
            ],
        }
        tone = "ok" if data.get("pushed") else ""
    elif kind == "confirmation.finished":
        role = "confirmation"
        ok = bool(data.get("ok"))
        title = "Confirmation passed" if ok else "Confirmation failed"
        body = str(data.get("target") or "—")
        facts = [
            f"exit {data.get('exit_code', '?')}",
            f"proof {str(data.get('output_sha256') or '')[:10]}",
        ]
        card = {
            "kind": "confirmation",
            "rows": [
                ["Result", "pass" if ok else "fail"],
                ["Target", str(data.get("target", "—"))],
                ["Output SHA", str(data.get("output_sha256", "—"))[:12]],
            ],
        }
        tone = "ok" if ok else "bad"
    elif kind == "deploy.finished":
        role = "delivery"
        status = str(data.get("status") or "unknown")
        title = {
            "deployed": "Deployed",
            "failed": "Deployment failed",
            "dry_run": "Deployment dry run",
        }.get(status, f"Deployment: {status}")
        body = f"{data.get('environment', '?')} A� {str(data.get('commit', '?'))[:12]}"
        facts = [f"exit {data.get('exit_code', '?')}", status]
        environment = str(data.get("environment", "-"))
        commit = str(data.get("commit", "-"))[:12]
        card = {
            "kind": "deploy",
            "rows": [
                ["Environment", environment],
                ["Commit", commit],
                ["Status", status],
            ],
        }
        tone = "ok" if status == "deployed" else "bad"
    elif kind == "escape.detected":
        role = "verifier"
        title = "Escape detected"
        body = str(data.get("subject") or "A released change came back.")
        facts = [str(data.get("kind") or "escape"), str(data.get("evidence_commit", ""))[:12]]
        tone = "bad"
    elif kind == "rework.detected":
        role = "verifier"
        title = "Rework detected"
        body = str(data.get("reason") or "A later task repeats the same source.")
        facts = [f"after {data.get('previous_task_id', '?')}"]
        tone = "bad"
    elif kind == "thread.agent":
        role = "mira"
        title = "Mira answered"
        body = str(data.get("answer") or "")
        facts = [
            f"model {data.get('model') or '-'}",
            f"{data.get('tokens') or 0} token(s)",
        ]
        generated_label = "AI answer"
        generated = True
        card = {
            "kind": "question",
            "rows": [["Question", str(data.get("question") or "")]],
        }
    elif kind == "thread.commentary":
        role = str(data.get("role") or "mira")
        title = {
            "builder": "Builder commentary",
            "inspector": "Inspector commentary",
            "reporter": "Reporter commentary",
        }.get(role, "Mira commentary")
        body = str(data.get("text") or "")
        facts = ["AI commentary", f"model {data.get('model') or '-'}"]
        generated_label = "AI commentary"
        generated = True
        card = None
    elif kind == "thread.discussion":
        role = str(data.get("role") or "mira")
        title = {
            "inspector": "Inspector discusses",
            "challenger": "Challenger discusses",
            "reporter": "Reporter discusses",
        }.get(role, "Team discussion")
        body = str(data.get("text") or "")
        stance = str(data.get("stance") or "")
        facts = ["AI discussion", f"model {data.get('model') or '-'}"]
        generated_label = "AI discussion"
        generated = True
        card = None
    elif kind == "thread.note":
        role = "person"
        title = "Context added"
        body = str(data.get("message") or "")
        facts = [f"by {data.get('by', 'a person')}"]
    elif kind == "note":
        raw_body = str(data.get("message") or "")
        if data.get("model"):
            role = "builder"
            title = "Proposal received"
            paths = data.get("paths") or []
            body = f"{data.get('model')} proposed a change to {len(paths)} file(s)."
            facts = [str(item) for item in paths]
        elif "v0" in raw_body and "release gate" in raw_body:
            role = "system"
            title = "Proof ready"
            body = "proof is ready; gate 2 is the next step"
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
            card = {
                "kind": "question",
                "prompt": "Release this commit?",
                "options": options,
            }
        else:
            role = "system"
            title = "Note"
            body = raw_body
    elif kind == "decision.shadow":
        role = "system"
        title = "LAIX shadow decision"
        body = f"{data.get('gate', 'gate')}: {data.get('reason_code', '')}"
        facts = [f"agree {data.get('agree', '—')}"]
    elif kind in ("wait.started", "wait.woken", "wait.expired"):
        role = "system"
        title = {
            "wait.started": "Waiting",
            "wait.woken": "Woke up",
            "wait.expired": "Wait expired",
        }[kind]
        body = str(data.get("wake_on") or data.get("on") or "")
    elif kind.startswith("memory."):
        role = "system"
        title = {
            "memory.reported": "PPMA synced",
            "memory.failed": "PPMA failed",
            "memory.recalled": "Memory recall",
            "memory.recall_failed": "Memory recall failed",
        }.get(kind, "Memory")
        body = str(data.get("error") or data.get("via") or "")
        facts = [f"{len(data.get('statements') or [])} statement(s)"]
        tone = "bad" if kind.endswith("failed") else ""
    elif kind == "state.changed":
        target = str(data.get("to") or "")
        if target not in ("blocked", "released", "reverted"):
            return None
        role = "system"
        title = f"State: {target}"
        body = str(data.get("reason") or "")
        tone = "bad" if target in ("blocked", "reverted") else "ok"
    elif kind == "preview.finished":
        role = "verifier"
        title = "Preview finished"
        body = f"Exit code {data.get('exit_code', '?')}."
        tone = "ok" if data.get("exit_code") == 0 else "bad"
    else:
        return None

    return {
        "seq": event.seq,
        "at": event.ts.isoformat(),
        "role": role,
        "type": kind,
        "title": title,
        "body": body,
        "facts": [item for item in facts if item],
        "tone": tone,
        "generated": bool(data.get("generated")) or generated,
        "generated_label": generated_label,
        "stance": stance,
        "card": card,
    }


def _thread(task: Task, events: list[Event]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for event in events:
        message = _thread_message(event, task)
        if message is not None:
            messages.append(message)
    return messages


def _thread_rail(
    task: Task,
    events: list[Event],
    run: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
    release: dict[str, Any],
    delivery: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
    team: dict[str, Any],
    verifier: dict[str, Any],
) -> dict[str, Any]:
    gates = [event.data for event in events if event.type == "gate.decided"]
    people = sorted({str(item.get("by") or "cli") for item in gates})
    owners = ((evidence or {}).get("risk") or {}).get("owners") or []
    challenge = (evidence or {}).get("challenge") or {}
    verdict = (evidence or {}).get("verdict") or {}
    agents = [
        {
            "role": "builder",
            "name": str((evidence or {}).get("model") or "—"),
            "detail": str((evidence or {}).get("provider") or "—"),
            "tone": "",
        },
        {
            "role": "challenger",
            "name": str(challenge.get("model") or "—"),
            "detail": "allow" if challenge.get("allow") else "block" if challenge else "not run",
            "tone": "ok" if challenge.get("allow") else "bad" if challenge else "",
        },
        {
            "role": "verifier",
            "name": str(verifier.get("name") or "local"),
            "detail": str(verifier.get("isolation") or "process"),
            "tone": "",
        },
        {
            "role": "team",
            "name": "inspector + challenger + reporter",
            "detail": str((team.get("latest") or {}).get("verdict") or "not run"),
            "tone": "ok"
            if (team.get("latest") or {}).get("verdict") == "allow"
            else "bad"
            if team.get("latest")
            else "",
        },
    ]
    deliverables = [
        {
            "label": "Proof",
            "value": str((evidence or {}).get("proof_sha256") or "—")[:12],
            "href": "",
        },
        {"label": "Commit", "value": str((run or {}).get("base_commit") or "—")[:12], "href": ""},
        {"label": "Branch", "value": str((delivery or {}).get("branch") or "—"), "href": ""},
        {
            "label": "Pull request",
            "value": str((delivery or {}).get("pr_url") or "—"),
            "href": str((delivery or {}).get("pr_url") or ""),
        },
        {
            "label": "Release",
            "value": "released" if release.get("released") else "not released",
            "href": "",
        },
        {
            "label": "Confirmation",
            "value": "pass"
            if (confirmation or {}).get("ok")
            else "fail"
            if confirmation
            else "not run",
            "href": "",
        },
    ]
    checks = [
        {
            "label": "Policy",
            "value": "pass" if ((evidence or {}).get("policy") or {}).get("ok") else "fail",
        },
        {
            "label": "Verdict",
            "value": "allow" if verdict.get("allow") else "block" if evidence else "—",
        },
        {
            "label": "Challenge",
            "value": "allow" if challenge.get("allow") else "block" if challenge else "not run",
        },
        {"label": "Team", "value": str((team.get("latest") or {}).get("verdict") or "not run")},
        {
            "label": "Confirmation",
            "value": "pass"
            if (confirmation or {}).get("ok")
            else "fail"
            if confirmation
            else "not run",
        },
    ]
    return {
        "task": {
            "id": task.id,
            "state": task.state.value,
            "product": task.product,
            "source": f"{task.source.kind.value}:{task.source.ref}",
            "title": task.source.title,
        },
        "factory": {
            "flow": task.flow,
            "run": str((run or {}).get("run_id") or "—"),
            "base_commit": str((run or {}).get("base_commit") or "—")[:12],
            "checks_sha": str((run or {}).get("checks_sha") or "—")[:12],
        },
        "people": people or ["—"],
        "owners": owners,
        "agents": agents,
        "deliverables": deliverables,
        "checks": checks,
        "cost": {
            "tokens": int((evidence or {}).get("tokens") or 0),
            "usd": float((evidence or {}).get("usd") or 0),
            "duration_ms": int((evidence or {}).get("duration_ms") or 0),
        },
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


class WorksHTTPServer(ThreadingHTTPServer):
    paths: WorksPaths
    writable: bool = False
    write_lock: threading.Lock
    live: LiveState

    def server_close(self) -> None:
        live = getattr(self, "live", None)
        if live is not None:
            live.stop()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    server_version = "WorksUI/0.1"
    sys_version = ""

    @property
    def paths(self) -> WorksPaths:
        return cast(WorksHTTPServer, self.server).paths

    @property
    def writable(self) -> bool:
        return cast(WorksHTTPServer, self.server).writable

    def do_HEAD(self) -> None:
        self._static(head=True)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/events":
            self._events()
            return
        if parsed.path.startswith("/api/"):
            self._api(parsed.path, parse_qs(parsed.query))
        else:
            self._static()

    def _drain_body(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if 0 < length <= 65_536:
            self.rfile.read(length)

    def do_POST(self) -> None:
        if not self.writable:
            self._drain_body()
            self._json(
                HTTPStatus.METHOD_NOT_ALLOWED,
                {"ok": False, "error": "read-only preview; start `works ui --write` to report"},
            )
            return
        if urlparse(self.path).path not in (
            "/api/tasks",
            "/api/readiness",
            "/api/actions",
            "/api/settings/builder",
            "/api/sources",
            "/api/ask/stream",
        ):
            self._drain_body()
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "unknown endpoint"})
            return
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self._drain_body()
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "local requests only"})
            return
        if self.headers.get("X-Works-Write") != "1":
            self._drain_body()
            self._json(
                HTTPStatus.FORBIDDEN,
                {"ok": False, "error": "missing X-Works-Write header"},
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 65_536:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid body size"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid JSON"})
            return
        if not isinstance(payload, dict):
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "body must be an object"})
            return
        try:
            path = urlparse(self.path).path
            if path == "/api/readiness":
                self._run_readiness(payload)
            elif path == "/api/actions":
                self._run_action(payload)
            elif path == "/api/settings/builder":
                self._save_builder_settings(payload)
            elif path == "/api/sources":
                self._run_source(payload)
            elif path == "/api/ask/stream":
                self._ask_stream(payload)
            else:
                self._create_task(payload)
        except (ConfigError, ValueError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception as exc:  # a write failure must not leak a trace
            LOG.warning("report failed: %s", exc, exc_info=True)
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})

    def _ask_stream(self, payload: dict[str, Any]) -> None:
        from works.application.assistant.chat import ask_mira_stream

        task_id = str(payload.get("task_id") or "").strip()
        question = str(payload.get("question") or "").strip()
        if not task_id or not question:
            raise ValueError("task_id and question are required")
        Queue(self.paths).load(task_id)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            for event in ask_mira_stream(self.paths, task_id, question):
                body = json.dumps(event, ensure_ascii=False, default=str)
                self.wfile.write(f"data: {body}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:  # after headers, an error is an SSE event
            try:
                body = json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False)
                self.wfile.write(f"data: {body}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

    def _run_readiness(self, payload: dict[str, Any]) -> None:
        from works.application.execution.readiness import assess

        repo_raw = str(payload.get("repo") or "").strip()
        if not repo_raw:
            raise ValueError("repository path is required")
        repo = Path(repo_raw).expanduser()
        repo = (Path.cwd() / repo).resolve() if not repo.is_absolute() else repo.resolve()
        if not repo.is_dir():
            raise ValueError(f"repository does not exist: {repo}")
        report = assess(repo, run_commands=True)
        self._json(HTTPStatus.OK, {"ok": report.status != "fail", **report.as_dict()})

    def _create_task(self, payload: dict[str, Any]) -> None:
        repo_raw = str(payload.get("repo") or "").strip()
        ref = str(payload.get("ref") or "").strip()
        title = str(payload.get("title") or "").strip()
        product = str(payload.get("product") or "openjiuwen").strip()
        flow = str(payload.get("flow") or "fix-issue").strip()
        if not product:
            raise ValueError("product is required")
        if repo_raw:
            repo = Path(repo_raw).expanduser()
            repo = (Path.cwd() / repo).resolve() if not repo.is_absolute() else repo.resolve()
        else:
            try:
                repo = resolve_repo(self.paths, product)
            except ConfigError as exc:
                raise ValueError(str(exc)) from exc
        if not repo.is_dir():
            raise ValueError(f"repository does not exist: {repo}")
        if not (repo / ".git").exists():
            raise ValueError(f"not a git repository: {repo}")
        if not ref or not title:
            raise ValueError("reference and title are required")
        if len(ref) > 120 or len(title) > 240:
            raise ValueError("reference or title is too long")
        try:
            source_kind = SourceKind(str(payload.get("kind") or "manual"))
        except ValueError as exc:
            raise ValueError("kind must be manual, tracker or detector") from exc
        try:
            task_kind = TaskKind(str(payload.get("task_kind") or "fix"))
        except ValueError as exc:
            raise ValueError("task_kind must be fix or check-change") from exc
        queue = Queue(self.paths)
        with cast(WorksHTTPServer, self.server).write_lock:
            task, created = queue.submit(
                source=Source(kind=source_kind, ref=ref, title=title),
                flow=flow,
                product=product,
                repo=str(repo),
                task_kind=task_kind,
            )
        self._json(
            HTTPStatus.CREATED if created else HTTPStatus.OK,
            {
                "ok": True,
                "created": created,
                "task": task.model_dump(mode="json"),
                "repo": str(repo),
                "url": f"#/task/{task.id}/story",
            },
        )

    def _run_action(self, payload: dict[str, Any]) -> None:
        action = str(payload.get("action") or "").strip()
        task_id = str(payload.get("task_id") or "").strip()
        if not task_id:
            raise ValueError("task_id is required")
        queue = Queue(self.paths)
        queue.load(task_id)
        with cast(WorksHTTPServer, self.server).write_lock:
            if action == "add-context":
                message = str(payload.get("message") or "").strip()
                if not message:
                    raise ValueError("message is required")
                if len(message) > 2000:
                    raise ValueError("message is too long")
                event = queue.append(
                    task_id,
                    "thread.note",
                    {"message": message, "by": "person"},
                )
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "action": action,
                        "event": event.model_dump(mode="json"),
                    },
                )
                return
            if action == "ask":
                from works.application.assistant.chat import ask_mira

                question = str(payload.get("question") or "").strip()
                answer = ask_mira(self.paths, task_id, question)
                self._json(
                    HTTPStatus.OK,
                    {"ok": True, "action": action, "answer": answer},
                )
                return
            if action == "commentary":
                from works.application.assistant.chat import generate_commentary

                messages = generate_commentary(self.paths, task_id)
                self._json(
                    HTTPStatus.OK,
                    {"ok": True, "action": action, "messages": messages},
                )
                return
            if action == "discussion":
                from works.application.assistant.chat import generate_discussion

                messages = generate_discussion(self.paths, task_id)
                self._json(
                    HTTPStatus.OK,
                    {"ok": True, "action": action, "messages": messages},
                )
                return
            if action == "approve-plan":
                from works.application.approvals.gates import approve_plan

                task, event = approve_plan(self.paths, task_id, by="ui")
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "action": action,
                        "task": task.model_dump(mode="json"),
                        "event": event.model_dump(mode="json"),
                    },
                )
                return
            if action == "release":
                from works.application.delivery.release import approve_release

                task, packet, created = approve_release(self.paths, task_id)
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "action": action,
                        "created": created,
                        "task": task.model_dump(mode="json"),
                        "release": packet.as_dict(),
                    },
                )
                return
            if action == "deliver":
                from works.application.delivery.deliver import deliver

                delivery = deliver(
                    self.paths,
                    task_id,
                    provider=str(payload.get("provider") or "none"),
                    tracker=payload.get("tracker") or None,
                    dry_run=bool(payload.get("dry_run")),
                )
                self._json(
                    HTTPStatus.OK,
                    {"ok": True, "action": action, "delivery": delivery.as_dict()},
                )
                return
            if action == "confirm":
                from works.application.delivery.confirm import confirm

                result = confirm(
                    self.paths,
                    task_id,
                    url=str(payload.get("url") or "").strip() or None,
                    command=payload.get("command"),
                    tracker=payload.get("tracker") or None,
                    close_issue=bool(payload.get("close")),
                    force=bool(payload.get("force")),
                )
                self._json(
                    HTTPStatus.OK,
                    {"ok": result.ok, "action": action, "confirmation": result.as_dict()},
                )
                return
            if action == "team-verify":
                from works.application.team.launcher import run_team_verify

                team_result = run_team_verify(self.paths, task_id)
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": team_result.get("verdict") == "allow",
                        "action": action,
                        "team": team_result,
                    },
                )
                return
        raise ValueError(f"unknown action {action!r}")

    def _run_source(self, payload: dict[str, Any]) -> None:
        source = str(payload.get("source") or "").strip()
        product = str(payload.get("product") or "").strip()
        repo_raw = str(payload.get("repo") or "").strip()
        try:
            limit = max(1, min(50, int(payload.get("limit") or 20)))
        except (TypeError, ValueError):
            limit = 20
        if source in ("github", "jira"):
            if not product:
                raise ValueError("product is required")
            try:
                repo = (
                    Path(repo_raw).expanduser().resolve()
                    if repo_raw
                    else resolve_repo(self.paths, product)
                )
            except ConfigError as exc:
                raise ValueError(str(exc)) from exc
            queue = Queue(self.paths)
            if source == "github":
                from works.application.intake.sources import github_issues, ingest_issues

                repository = str(payload.get("repository") or "").strip()
                if not repository:
                    raise ValueError("repository is required (owner/name)")
                issues = github_issues(
                    repository,
                    label=str(payload.get("label") or "").strip() or None,
                    limit=limit,
                )
            else:
                from works.application.intake.sources import ingest_issues, jira_issues

                url = str(payload.get("url") or "").strip()
                jql = str(payload.get("jql") or "").strip()
                if not url or not jql:
                    raise ValueError("Jira needs url and jql")
                issues = jira_issues(url, jql, limit=limit)
            with cast(WorksHTTPServer, self.server).write_lock:
                created = ingest_issues(queue, product=product, repo=str(repo), issues=issues)
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "source": source,
                    "found": len(issues),
                    "created": sum(1 for _, was_created in created if was_created),
                    "tasks": [task.id for task, _ in created],
                },
            )
            return
        if source == "detector":
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("detector name is required")
            with cast(WorksHTTPServer, self.server).write_lock:
                created = ingest_named(self.paths, name)
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "source": source,
                    "found": len(created),
                    "created": sum(1 for _, was_created in created if was_created),
                    "tasks": [task.id for task, _ in created],
                },
            )
            return
        raise ValueError(f"unknown source {source!r}")

    def _save_builder_settings(self, payload: dict[str, Any]) -> None:
        from works.application.settings import builder_health, save_builder_settings

        settings = save_builder_settings(self.paths, payload)
        self._json(HTTPStatus.OK, {"ok": True, "builder": builder_health(self.paths, settings)})

    def _api(self, path: str, query: dict[str, list[str]]) -> None:
        queue = Queue(self.paths)
        try:
            if path == "/api/health":
                from works.application.assistant.chat import availability
                from works.application.settings import builder_health, load_builder_settings

                try:
                    settings = load_builder_settings(self.paths)
                except ConfigError:
                    settings = None
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "readonly": not self.writable,
                        "write": self.writable,
                        "root": str(self.paths.root),
                        "version": "0.0.1",
                        "ai": availability(),
                        "builder": builder_health(self.paths, settings),
                    },
                )
                return
            if path == "/api/products":
                self._json(HTTPStatus.OK, {"ok": True, **product_map(self.paths)})
                return
            if path == "/api/detectors":
                refresh = query.get("refresh", ["0"])[0] in ("1", "true", "yes")
                self._json(HTTPStatus.OK, {"ok": True, **detector_map(self.paths, refresh=refresh)})
                return
            if path == "/api/tasks":
                limit_raw = query.get("limit", ["200"])[0]
                try:
                    limit = max(1, min(1000, int(limit_raw)))
                except ValueError:
                    limit = 200
                self._json(HTTPStatus.OK, {"tasks": _tasks(queue, limit)})
                return
            if path.startswith("/api/tasks/") and "/artifacts/" in path:
                self._artifact(path)
                return
            if path.startswith("/api/tasks/") and "/export/" in path:
                self._export(path)
                return
            if path.startswith("/api/tasks/") and path.endswith("/runs"):
                task_id = unquote(path.removeprefix("/api/tasks/").removesuffix("/runs"))
                self._json(HTTPStatus.OK, {"runs": _run_summaries(self.paths, task_id)})
                return
            if path.startswith("/api/tasks/"):
                task_id = unquote(path.removeprefix("/api/tasks/"))
                self._json(HTTPStatus.OK, _task_detail(queue, self.paths, task_id))
                return
            if path == "/api/metrics":
                metrics = collect(queue, Ledger(self.paths.ledger))
                self._json(HTTPStatus.OK, {"metrics": metrics.model_dump(mode="json")})
                return
            if path == "/api/ledger":
                rows = Ledger(self.paths.ledger).rows()
                self._json(
                    HTTPStatus.OK,
                    {"rows": [row.model_dump(mode="json") for row in rows[-200:]]},
                )
                return
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "unknown endpoint"})
        except Exception as exc:
            LOG.debug("api error", exc_info=True)
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": str(exc)})

    def _export(self, path: str) -> None:
        rest = unquote(path.removeprefix("/api/tasks/"))
        task_id, separator, kind = rest.partition("/export/")
        if not separator or not task_id or not kind:
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "export not found"})
            return
        found = _export(self.paths, task_id, kind)
        if found is None:
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "export not found"})
            return
        target, filename = found
        body = target.read_bytes()
        self._respond(
            HTTPStatus.OK,
            _content_type(target),
            body,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def _artifact(self, path: str) -> None:
        rest = unquote(path.removeprefix("/api/tasks/"))
        task_id, separator, name = rest.partition("/artifacts/")
        if not separator or not task_id or not name:
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "artifact not found"})
            return
        run_info = _run_index(self.paths).get(task_id)
        if run_info is None:
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "run not found"})
            return
        root = (run_info[1] / "artifacts").resolve()
        target = (root / name).resolve()
        if root not in target.parents or not target.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "artifact not found"})
            return
        body = target.read_bytes()
        self._respond(
            HTTPStatus.OK,
            _content_type(target),
            body,
            headers={"Content-Disposition": f'inline; filename="{target.name}"'},
        )

    def _events(self) -> None:
        server = cast(WorksHTTPServer, self.server)
        channel = server.live.subscribe()
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    payload = channel.get(timeout=15)
                except thread_queue.Empty:
                    self.wfile.write(b": ping\n\n")
                else:
                    body = json.dumps(payload, ensure_ascii=False, default=str)
                    self.wfile.write(f"data: {body}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            self.close_connection = True
        finally:
            server.live.unsubscribe(channel)

    def _static(self, *, head: bool = False) -> None:
        name = urlparse(self.path).path.lstrip("/")
        dist = _dist_asset(name)
        if dist is not None:
            body = dist.read_bytes()
            self._respond(HTTPStatus.OK, _content_type(dist), body, head=head)
            return
        if name not in STATIC:
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        path = ASSETS / STATIC[name]
        if not path.exists():
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "asset missing"})
            return
        body = path.read_bytes()
        self._respond(HTTPStatus.OK, _content_type(path), body, head=head)

    def _respond(
        self,
        status: HTTPStatus,
        content_type: str,
        body: bytes,
        *,
        headers: dict[str, str] | None = None,
        head: bool = False,
    ) -> None:
        """Write one response; a browser that navigated away is not a server error."""
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if not head:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            self.close_connection = True

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._respond(status, "application/json; charset=utf-8", body)

    def log_message(self, format: str, *args: Any) -> None:
        LOG.debug(format, *args)


def _dist_asset(name: str) -> Path | None:
    if not DIST.is_dir():
        return None
    if name in ("", "index.html"):
        target = DIST / "index.html"
    elif name.startswith("assets/"):
        target = (DIST / name).resolve()
    else:
        return None
    if DIST.resolve() not in target.parents and target != DIST / "index.html":
        return None
    return target if target.is_file() else None


def _content_type(path: Path) -> str:
    return {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".ico": "image/x-icon",
        ".woff2": "font/woff2",
        ".map": "application/json",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".json": "application/json",
        ".txt": "text/plain; charset=utf-8",
        ".log": "text/plain; charset=utf-8",
        ".trace": "application/json",
    }.get(path.suffix, "application/octet-stream")


def serve(
    paths: WorksPaths,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    write: bool = False,
) -> WorksHTTPServer:
    server = WorksHTTPServer((host, port), Handler)
    server.paths = paths
    server.writable = write
    server.write_lock = threading.Lock()
    server.live = LiveState(paths)
    server.live.start()
    return server
