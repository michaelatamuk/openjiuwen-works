from __future__ import annotations

import json
import logging

from works.logs import JsonFormatter


def test_a_log_line_is_json_with_context() -> None:
    record = logging.LogRecord(
        name="works.supervisor",
        level=logging.INFO,
        pathname="supervisor.py",
        lineno=42,
        msg="run finished",
        args=(),
        exc_info=None,
    )
    record.run_id = "r-1"
    record.task_id = "t-1"
    record.step = "verify"
    record.duration_ms = 12
    record.tokens = 30
    record.usd = 0.001
    payload = json.loads(JsonFormatter().format(record))
    assert payload["level"] == "info"
    assert payload["logger"] == "works.supervisor"
    assert payload["message"] == "run finished"
    assert payload["run_id"] == "r-1"
    assert payload["task_id"] == "t-1"
    assert payload["step"] == "verify"
    assert payload["duration_ms"] == 12
    assert payload["tokens"] == 30
    assert payload["usd"] == 0.001


def test_absent_context_is_omitted_not_null() -> None:
    record = logging.LogRecord(
        name="works",
        level=logging.WARNING,
        pathname="x.py",
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    payload = json.loads(JsonFormatter().format(record))
    assert "run_id" not in payload
    assert payload["level"] == "warning"
