"""Response models for the local API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Health(BaseModel):
    ok: bool
    readonly: bool
    write: bool
    root: str
    version: str
    ai: dict[str, Any]
    builder: dict[str, Any] | None = None
