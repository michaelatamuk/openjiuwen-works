"""Every persisted schema, printed by `works schema`."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .evidence import Evidence
from .records import (
    SCHEMA_VERSION,
    CommandRecord,
    Event,
    LedgerRow,
    RunRecord,
    Task,
    Verdict,
)


def all_schemas() -> dict[str, Any]:
    models: dict[str, type[BaseModel]] = {
        "task": Task,
        "event": Event,
        "run": RunRecord,
        "verdict": Verdict,
        "ledger": LedgerRow,
        "command": CommandRecord,
        "evidence": Evidence,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "schemas": {name: model.model_json_schema() for name, model in models.items()},
    }
