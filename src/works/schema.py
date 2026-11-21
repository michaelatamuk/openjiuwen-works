"""Every persisted schema, printed by `works schema`."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .decision import GateContext, GateVerdict
from .evidence import Evidence
from .flakes import Flake
from .harness.base import Proposal
from .records import (
    SCHEMA_VERSION,
    Challenge,
    CommandRecord,
    Event,
    Finding,
    LedgerRow,
    RunRecord,
    Task,
    Verdict,
)
from .risk import RiskRating


def all_schemas() -> dict[str, Any]:
    models: dict[str, type[BaseModel]] = {
        "task": Task,
        "event": Event,
        "run": RunRecord,
        "verdict": Verdict,
        "ledger": LedgerRow,
        "command": CommandRecord,
        "evidence": Evidence,
        "proposal": Proposal,
        "finding": Finding,
        "challenge": Challenge,
        "risk": RiskRating,
        "decision": GateVerdict,
        "gate_context": GateContext,
        "flake": Flake,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "schemas": {name: model.model_json_schema() for name, model in models.items()},
    }
