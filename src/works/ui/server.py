"""A read-only preview of the factory: queue, task, proof, risk and decisions."""

from __future__ import annotations

import json
import logging
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlparse

from ..config import WorksPaths
from ..errors import ConfigError
from ..ledger import Ledger
from ..metrics import collect
from ..queue import Queue
from ..records import Event, Source, SourceKind, Task, TaskKind

LOG = logging.getLogger("works.ui")
STATIC = {
    "": "index.html",
    "index.html": "index.html",
    "app.css": "app.css",
    "app.js": "app.js",
    "mira.svg": "mira.svg",
}
ASSETS = Path(__file__).parent / "static"


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
    from ..readiness import assess

    return assess(repo, run_commands=False).as_dict()


def feature_map(repo: Path, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    from ..features import feature_summary

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


def _pipeline(task: Task, events: list[Event], evidence: dict[str, Any] | None) -> dict[str, Any]:
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
        "released": 9,
    }.get(state, 0)
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
            return [f"back to {task.source.kind.value}:{task.source.ref}"]
        return ["awaiting confirmation"]

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
        None,
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
            label = (
                f"Release to {task.product}"
                if state == "proved"
                else f"Back in {task.product}"
                if state == "released"
                else f"Deliver to {task.product}"
            )
            caption = (
                f"The fix is ready to go back to {task.product}."
                if state == "proved"
                else f"The fix is back in {task.product}."
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
            story_artifacts = (
                ["The fix went back to the source"]
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


def _task_detail(queue: Queue, paths: WorksPaths, task_id: str) -> dict[str, Any]:
    task = queue.load(task_id)
    events = queue.events(task_id)
    runs = _run_index(paths)
    run_info = runs.get(task_id)
    run: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    proof_md = ""
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
    return {
        "task": task.model_dump(mode="json"),
        "summary": _task_summary(task, events),
        "run": run,
        "evidence": evidence,
        "proof_md": proof_md,
        "timeline": timeline,
        "pipeline": _pipeline(task, events, evidence),
        "readiness": readiness(Path(task.repo)),
        "features": feature_map(Path(task.repo), evidence),
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
        if urlparse(self.path).path not in ("/api/tasks", "/api/readiness"):
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
            if urlparse(self.path).path == "/api/readiness":
                self._run_readiness(payload)
            else:
                self._create_task(payload)
        except (ConfigError, ValueError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception as exc:  # a write failure must not leak a trace
            LOG.warning("report failed: %s", exc, exc_info=True)
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})

    def _run_readiness(self, payload: dict[str, Any]) -> None:
        from ..readiness import assess

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
        if not repo_raw:
            raise ValueError("repository path is required")
        repo = Path(repo_raw).expanduser()
        repo = (Path.cwd() / repo).resolve() if not repo.is_absolute() else repo.resolve()
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
                "url": f"#/task/{task.id}/story",
            },
        )

    def _api(self, path: str, query: dict[str, list[str]]) -> None:
        queue = Queue(self.paths)
        try:
            if path == "/api/health":
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "readonly": not self.writable,
                        "write": self.writable,
                        "root": str(self.paths.root),
                        "version": "0.0.1",
                    },
                )
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
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", _content_type(target))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", f'inline; filename="{target.name}"')
        self.end_headers()
        self.wfile.write(body)

    def _static(self, *, head: bool = False) -> None:
        name = urlparse(self.path).path.lstrip("/")
        if name not in STATIC:
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        path = ASSETS / STATIC[name]
        if not path.exists():
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "asset missing"})
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", _content_type(path))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        LOG.debug(format, *args)


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
    return server
