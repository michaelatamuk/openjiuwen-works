"""Structured JSON logs. Nothing in this package calls print()."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the fields the standard requires."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("run_id", "task_id", "step", "duration_ms", "tokens", "usd"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure(level: str = "INFO", *, stream: Any = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("works")
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"works.{name}")


def bound(logger: logging.Logger, **fields: Any) -> logging.LoggerAdapter[logging.Logger]:
    return logging.LoggerAdapter(logger, fields)
