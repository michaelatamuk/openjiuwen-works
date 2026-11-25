"""Task and run response models.

Nested sections that are still evolving stay as plain JSON objects; the top-level keys and the
summary fields are typed so the generated client has stable names.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TaskSummary(BaseModel):
    id: str
    state: str
    flow: str
    product: str
    source: str
    title: str
    kind: str
    updated_at: str
    risk: str | None = None
    decision: str | None = None
    would_block: int
    waiting_on: str | None = None


class TaskList(BaseModel):
    tasks: list[TaskSummary]


class RunSummary(BaseModel):
    run_id: str
    state: str
    finished_at: str
    base_commit: str
    proof_sha256: str
    verdict: str
    risk: str
    tokens: int
    usd: float
    duration_ms: int
    files: list[str]
    not_tested: list[str]
    delivered: bool
    confirmed: bool


class RunList(BaseModel):
    runs: list[RunSummary]


class TaskDetail(BaseModel):
    task: dict[str, Any]
    summary: TaskSummary
    run: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    proof_md: str = ""
    timeline: list[dict[str, Any]]
    pipeline: dict[str, Any]
    plan: dict[str, Any] | None = None
    plan_diff: str | None = None
    readiness: dict[str, Any]
    features: dict[str, Any]
    release: dict[str, Any]
    delivery: dict[str, Any] | None = None
    deployment: dict[str, Any] | None = None
    confirmation: dict[str, Any] | None = None
    team: dict[str, Any]
    laix: list[dict[str, Any]]
    verifier: dict[str, Any]
    artifacts: list[dict[str, Any]]
    runs: list[RunSummary]
    thread: list[dict[str, Any]]
    rail: dict[str, Any]
