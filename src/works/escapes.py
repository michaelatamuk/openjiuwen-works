"""Escape and rework attribution: did a released fix come back to us?

An escape is a revert or a hotfix that touches the same paths as a delivered commit inside the
release window. Rework is a later task that repeats the same source reference. Both are derived
from recorded evidence (git history, ledger, queue), never from a model's claim.

This is deliberately a local, auditable first version: a remote main/CI signal can feed the same
report later, but the classification code and the report shape are already here.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .config import WorksPaths
from .ledger import Ledger
from .queue import Queue
from .records import Event, TaskState
from .runner import CommandRunner, SubprocessRunner

_REVERT_RE = re.compile(r"(?i)this reverts commit ([0-9a-f]{7,40})")
_DEFAULT_DAYS = 14
_REPORT = "escapes.json"


class EscapeKind(StrEnum):
    REVERT = "revert"
    HOTFIX = "hotfix"


class EscapeFinding(BaseModel):
    task_id: str
    run_id: str
    commit: str
    kind: EscapeKind
    evidence_commit: str
    subject: str
    paths: list[str] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class ReworkFinding(BaseModel):
    task_id: str
    previous_task_id: str
    source_ref: str
    reason: str


class EscapeReport(BaseModel):
    schema_version: int = 1
    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    window_days: int
    findings: list[EscapeFinding] = Field(default_factory=list)
    rework: list[ReworkFinding] = Field(default_factory=list)

    @property
    def escapes(self) -> int:
        return len(self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "window_days": self.window_days,
            "escapes": self.escapes,
            "rework": len(self.rework),
            "findings": [item.model_dump(mode="json") for item in self.findings],
            "rework_items": [item.model_dump(mode="json") for item in self.rework],
        }


def _json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _delivery(paths: WorksPaths, run_id: str) -> dict[str, Any] | None:
    return _json(paths.run_dir(run_id) / "delivery.json")


def _changed_paths(paths: WorksPaths, run_id: str) -> list[str]:
    evidence = _json(paths.run_dir(run_id) / "evidence.json") or {}
    files = evidence.get("files_changed")
    if isinstance(files, list):
        return [str(item) for item in files]
    return []


def _git_log(runner: CommandRunner, repo: Path, since: datetime) -> str:
    result = runner.run(
        [
            "git",
            "log",
            f"--since={since.isoformat()}",
            "--pretty=format:%H%x1f%s%x1f%b%x1e",
        ],
        repo,
        timeout_s=60,
    )
    return result.stdout


def _commit_paths(runner: CommandRunner, repo: Path, commit: str) -> list[str]:
    result = runner.run(
        ["git", "show", "--name-only", "--pretty=format:", commit],
        repo,
        timeout_s=60,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _parse_commits(text: str) -> list[tuple[str, str, str]]:
    commits: list[tuple[str, str, str]] = []
    for record in text.split("\x1e"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) < 2:
            continue
        commit = parts[0].strip()
        subject = parts[1].strip()
        body = parts[2].strip() if len(parts) > 2 else ""
        if commit:
            commits.append((commit, subject, body))
    return commits


def _classify(
    task_id: str,
    run_id: str,
    commit: str,
    changed: list[str],
    commits: list[tuple[str, str, str]],
) -> list[EscapeFinding]:
    findings: list[EscapeFinding] = []
    lowered = {path.lower() for path in changed}
    for evidence_commit, subject, body in commits:
        revert = _REVERT_RE.search(f"{subject}\n{body}")
        if revert is not None:
            reverted = revert.group(1).lower()
            if commit.lower().startswith(reverted) or reverted.startswith(commit.lower()[:7]):
                findings.append(
                    EscapeFinding(
                        task_id=task_id,
                        run_id=run_id,
                        commit=commit,
                        kind=EscapeKind.REVERT,
                        evidence_commit=evidence_commit,
                        subject=subject,
                        paths=changed,
                    )
                )
                continue
        text = subject.lower()
        if "hotfix" in text and lowered:
            findings.append(
                EscapeFinding(
                    task_id=task_id,
                    run_id=run_id,
                    commit=commit,
                    kind=EscapeKind.HOTFIX,
                    evidence_commit=evidence_commit,
                    subject=subject,
                    paths=changed,
                )
            )
    return findings


def scan(
    paths: WorksPaths,
    *,
    days: int = _DEFAULT_DAYS,
    runner: CommandRunner | None = None,
) -> EscapeReport:
    """Scan the release window for reverts and hotfixes, plus repeated source references."""
    if days <= 0:
        raise ValueError("the escape window must be positive")
    queue = Queue(paths)
    ledger = Ledger(paths.ledger)
    command_runner = runner or SubprocessRunner()
    now = datetime.now(tz=UTC)
    window = timedelta(days=days)
    report = EscapeReport(window_days=days, generated_at=now)

    for row in ledger.rows():
        if row.state is not TaskState.RELEASED or not row.run_id:
            continue
        delivery = _delivery(paths, row.run_id)
        if not delivery or not delivery.get("commit"):
            continue
        commit = str(delivery["commit"])
        task = queue.load(row.task_id)
        repo = Path(task.repo)
        if not repo.exists():
            continue
        since = max(row.ts, now - window)
        commits = _parse_commits(_git_log(command_runner, repo, since))
        changed = _changed_paths(paths, row.run_id)
        findings: list[EscapeFinding] = []
        for item in _classify(row.task_id, row.run_id, commit, changed, commits):
            if item.kind is EscapeKind.HOTFIX:
                item.paths = _commit_paths(command_runner, repo, item.evidence_commit) or changed
                item_paths = {path.lower() for path in item.paths}
                release_paths = {path.lower() for path in changed}
                if not item_paths & release_paths:
                    continue
            findings.append(item)
        report.findings.extend(findings)

    seen: set[str] = set()
    for row in ledger.rows():
        if row.state is not TaskState.RELEASED:
            continue
        seen.add(row.task_id)
        released_at = row.ts
        for task in queue.list_tasks():
            if task.id in seen or task.id == row.task_id:
                continue
            if task.created_at <= released_at or task.created_at - released_at > window:
                continue
            if task.source.ref == queue.load(row.task_id).source.ref:
                report.rework.append(
                    ReworkFinding(
                        task_id=task.id,
                        previous_task_id=row.task_id,
                        source_ref=task.source.ref,
                        reason="a later task repeats the same source reference",
                    )
                )

    return report


def write_report(paths: WorksPaths, report: EscapeReport) -> Path:
    path = paths.root / _REPORT
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def read_report(paths: WorksPaths) -> EscapeReport | None:
    path = paths.root / _REPORT
    if not path.exists():
        return None
    try:
        return EscapeReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _event_key(event: Event) -> tuple[str, str | None, str | None]:
    if event.type == "rework.detected":
        return (event.type, event.data.get("previous_task_id"), None)
    return (event.type, event.data.get("kind"), event.data.get("evidence_commit"))


def append_events(paths: WorksPaths, report: EscapeReport) -> None:
    """Record one event per new finding; a second scan is idempotent."""
    queue = Queue(paths)
    for task_id in {item.task_id for item in report.findings + report.rework}:
        existing: set[tuple[str, str | None, str | None]] = {
            _event_key(event) for event in queue.events(task_id)
        }
        for finding in [item for item in report.findings if item.task_id == task_id]:
            key: tuple[str, str | None, str | None] = (
                "escape.detected",
                finding.kind.value,
                finding.evidence_commit,
            )
            if key not in existing:
                queue.append(
                    task_id,
                    "escape.detected",
                    {
                        "kind": finding.kind.value,
                        "commit": finding.commit,
                        "evidence_commit": finding.evidence_commit,
                        "subject": finding.subject,
                    },
                )
                existing.add(key)
        for rework in [item for item in report.rework if item.task_id == task_id]:
            key = ("rework.detected", rework.previous_task_id, None)
            if key not in existing:
                queue.append(
                    task_id,
                    "rework.detected",
                    {
                        "previous_task_id": rework.previous_task_id,
                        "source_ref": rework.source_ref,
                        "reason": rework.reason,
                    },
                )
                existing.add(key)
