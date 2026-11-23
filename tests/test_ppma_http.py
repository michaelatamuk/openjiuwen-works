from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

from tests.test_evidence import fixed_evidence
from works.application.memory.ppma import PpmaMemory
from works.domain.records import RunRecord, Source, SourceKind, StopReason, Task, TaskState


class _PpmaStub(BaseHTTPRequestHandler):
    messages: ClassVar[list[dict]] = []
    duplicates: ClassVar[int] = 0

    def log_message(self, format: str, *args) -> None:
        return

    def _json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self) -> None:
        if self.path == "/v0/apps/works/manifest":
            self._json(HTTPStatus.OK, {"app": "works"})
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_GET(self) -> None:
        if self.path == "/v0/spaces/me/memory/views/about_me":
            self._json(
                HTTPStatus.OK,
                {
                    "view": "about_me",
                    "version": 1,
                    "statements": [
                        {"id": "s1", "text": "The last fix touched render/preview.c"},
                        {"id": "s2", "text": "Flaky tests are blocked, not retried"},
                    ],
                },
            )
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/v0/apps/works/token":
            self._json(HTTPStatus.OK, {"token": "app-token"})
            return
        if self.path == "/v0/spaces/me/messages":
            ids = {message["id"] for message in self.messages}
            accepted = []
            duplicates = []
            for message in payload.get("messages", []):
                if message["id"] in ids:
                    duplicates.append(message["id"])
                else:
                    self.messages.append(message)
                    accepted.append(message["id"])
            type(self).duplicates += len(duplicates)
            self._json(
                HTTPStatus.ACCEPTED,
                {"accepted": accepted, "duplicates": duplicates},
            )
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})


def test_ppma_contract_over_real_http_is_idempotent() -> None:
    _PpmaStub.messages = []
    _PpmaStub.duplicates = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PpmaStub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        evidence = fixed_evidence().bind()
        task = Task(
            id="t-http",
            flow="fix-issue",
            product="openjiuwen",
            repo=".",
            source=Source(kind=SourceKind.MANUAL, ref="GH-1", title="bug"),
        )
        now = datetime.now(tz=UTC)
        record = RunRecord(
            run_id=evidence.run_id,
            task_id=task.id,
            flow="fix-issue",
            state=TaskState.PROVED,
            stop_reason=StopReason.COMPLETED,
            started_at=now,
            finished_at=now,
        )
        memory = PpmaMemory(
            f"http://{host}:{port}",
            owner_token="owner",  # noqa: S106 - a test token
        )
        memory.record(task=task, record=record, evidence=evidence)
        memory.record(task=task, record=record, evidence=evidence)
        recalled = memory.recall(limit=1)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert recalled == ["The last fix touched render/preview.c"]
    assert len(_PpmaStub.messages) == 1
    assert _PpmaStub.duplicates == 1
    assert _PpmaStub.messages[0]["type"] == "works.run_finished"
