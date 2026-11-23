"""Shared schema version and clock for persisted records."""

from __future__ import annotations

from datetime import UTC, datetime

SCHEMA_VERSION = 1


def utcnow() -> datetime:
    return datetime.now(tz=UTC)
