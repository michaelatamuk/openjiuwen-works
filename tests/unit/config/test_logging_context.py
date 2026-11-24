from __future__ import annotations

import json
import logging

from works.config.logging import JsonFormatter


def test_request_and_job_ids_are_logged() -> None:
    record = logging.LogRecord(
        name="works.http",
        level=logging.INFO,
        pathname="app.py",
        lineno=1,
        msg="GET /api/v1/health 200",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-1"
    record.job_id = "j-1"
    record.method = "GET"
    record.path = "/api/v1/health"
    record.status = 200
    payload = json.loads(JsonFormatter().format(record))
    assert payload["request_id"] == "req-1"
    assert payload["job_id"] == "j-1"
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/v1/health"
    assert payload["status"] == 200
