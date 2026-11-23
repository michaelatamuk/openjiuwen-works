"""Compatibility re-exports for domain records.

New code should import from the narrow module (`task`, `event`, `run`, `ledger`, `enums`).
"""

from __future__ import annotations

from .base import SCHEMA_VERSION, utcnow
from .enums import Priority, SourceKind, StopReason, TaskKind, TaskState
from .event import Event, Finding
from .ledger import LedgerRow
from .run import Challenge, CommandRecord, RunRecord, ScenarioOutcome, Verdict
from .task import Budget, Scope, Source, Task

__all__ = [
    "SCHEMA_VERSION",
    "Budget",
    "Challenge",
    "CommandRecord",
    "Event",
    "Finding",
    "LedgerRow",
    "Priority",
    "RunRecord",
    "ScenarioOutcome",
    "Scope",
    "Source",
    "SourceKind",
    "StopReason",
    "Task",
    "TaskKind",
    "TaskState",
    "Verdict",
    "utcnow",
]
