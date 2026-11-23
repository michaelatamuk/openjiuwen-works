"""Approved-plan memory.

Only approved plans enter this file. A new plan can recall similar patterns, but the prompt still
treats them as data; the flow and scenario set remain the contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .config import WorksPaths
from .errors import ConfigError

MEMORY_PATH = Path("plans") / "memory.jsonl"


class PlanMemoryRecord(BaseModel):
    task_id: str
    plan_id: str
    product: str
    flow: str
    summary: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    hash: str = ""
    approved_by: str = ""
    approved_at: str = ""


class PlanMemory:
    def __init__(self, paths: WorksPaths) -> None:
        self._paths = paths

    @property
    def path(self) -> Path:
        return self._paths.root / MEMORY_PATH

    def remember(self, plan: Any, *, by: str) -> PlanMemoryRecord:
        approved_at = plan.approved_at.isoformat() if plan.approved_at else ""
        record = PlanMemoryRecord(
            task_id=plan.task_id,
            plan_id=plan.plan_id,
            product=plan.product,
            flow=plan.flow,
            summary=plan.summary,
            steps=[step.model_dump(mode="json") for step in plan.steps],
            hash=plan.hash,
            approved_by=by,
            approved_at=approved_at,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._load()
        if any(item.plan_id == record.plan_id for item in existing):
            return record
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(record.model_dump_json() + "\n")
        return record

    def recall(self, *, product: str, flow: str, limit: int = 3) -> list[dict[str, Any]]:
        items = [item for item in self._load() if item.product == product and item.flow == flow]
        seen: set[str] = set()
        selected: list[dict[str, Any]] = []
        for item in reversed(items):
            if item.plan_id in seen:
                continue
            seen.add(item.plan_id)
            selected.append(item.model_dump(mode="json"))
            if len(selected) >= limit:
                break
        return selected

    def _load(self) -> list[PlanMemoryRecord]:
        if not self.path.exists():
            return []
        records: list[PlanMemoryRecord] = []
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(PlanMemoryRecord.model_validate_json(line))
            except ValueError as exc:
                raise ConfigError(
                    f"{self.path}:{number} is not a valid plan memory: {exc}"
                ) from exc
        return records
