"""A read-only preview of the factory: queue, task, proof, risk and decisions."""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlparse

from ..config import WorksPaths
from ..ledger import Ledger
from ..metrics import collect
from ..queue import Queue
from ..records import Event, Task

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
    checks = [
        ("git", "Git repository", (repo / ".git").exists()),
        ("flow", "Flow definition", (repo / "flows").exists()),
        ("project", "Python project", (repo / "pyproject.toml").exists()),
        ("tests", "Test suite", (repo / "tests").exists()),
        ("readme", "Repository map", (repo / "README.md").exists()),
    ]
    passed = sum(1 for _, _, ok in checks if ok)
    return {
        "available": True,
        "status": "pass" if passed == len(checks) else "fail",
        "passed": passed,
        "total": len(checks),
        "checks": [{"id": key, "label": label, "ok": ok} for key, label, ok in checks],
        "note": "Basic preview; the full readiness gate is T2.18.",
    }


def feature_map(repo: Path) -> dict[str, Any]:
    directory = repo / "features"
    files = sorted(directory.glob("*.yaml")) if directory.exists() else []
    return {
        "available": bool(files),
        "files": [path.name for path in files],
        "note": "Feature coverage lands with T2.19." if not files else "",
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
        "readiness": readiness(Path(task.repo)),
        "features": feature_map(Path(task.repo)),
    }


def _tasks(queue: Queue, limit: int) -> list[dict[str, Any]]:
    tasks = queue.list_tasks()
    items = [_task_summary(task, queue.events(task.id)) for task in tasks]
    items.sort(key=lambda item: str(item["updated_at"]), reverse=True)
    return items[:limit]


class WorksHTTPServer(ThreadingHTTPServer):
    paths: WorksPaths


class Handler(BaseHTTPRequestHandler):
    server_version = "WorksUI/0.1"
    sys_version = ""

    @property
    def paths(self) -> WorksPaths:
        return cast(WorksHTTPServer, self.server).paths

    def do_HEAD(self) -> None:
        self._static(head=True)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._api(parsed.path, parse_qs(parsed.query))
        else:
            self._static()

    def do_POST(self) -> None:
        self._json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"ok": False, "error": "read-only preview; no write actions"},
        )

    def _api(self, path: str, query: dict[str, list[str]]) -> None:
        queue = Queue(self.paths)
        try:
            if path == "/api/health":
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "readonly": True,
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
    }.get(path.suffix, "application/octet-stream")


def serve(paths: WorksPaths, *, host: str = "127.0.0.1", port: int = 8765) -> WorksHTTPServer:
    server = WorksHTTPServer((host, port), Handler)
    server.paths = paths
    return server
