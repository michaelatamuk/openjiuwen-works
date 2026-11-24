"""A read-only preview of the factory: queue, task, proof, risk and decisions."""

from __future__ import annotations

import json
import logging
import queue as thread_queue
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlparse

from works.adapters.queue.ledger import Ledger
from works.adapters.queue.store import Queue
from works.application.intake.detectors import ingest_named
from works.application.intake.products import resolve_repo
from works.application.observability.metrics import collect
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError
from works.domain.records import Source, SourceKind, TaskKind
from works.interfaces.api.live import LiveState
from works.interfaces.api.presenters.story import _first, _first_at, _pipeline  # noqa: F401
from works.interfaces.api.presenters.tasks import (
    _export,
    _run_index,
    _run_summaries,
    _task_detail,
    _tasks,
    detector_map,
    product_map,
)
from works.interfaces.api.presenters.thread import (  # noqa: F401
    _thread,
    _thread_message,
    _thread_rail,
)
from works.interfaces.api.static import ASSETS, STATIC, _content_type, _dist_asset

LOG = logging.getLogger("works.ui")


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
