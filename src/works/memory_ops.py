"""Backfill finished runs into PPMA without re-running the factory.

The live supervisor reports a run when it finishes. This module is the recovery path for runs
created before PPMA was configured, for demo workspaces and for a PPMA outage: every run already
has `run.json` and `evidence.json`, so the same idempotent `works.run_finished` event can be sent
later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from .config import WorksPaths
from .evidence import Evidence
from .memory import Memory
from .queue import Queue
from .records import RunRecord, Task

Status = Literal["reported", "skipped", "failed", "dry-run"]


@dataclass(frozen=True)
class BackfillEntry:
    run_id: str
    task_id: str
    status: Status
    error: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "status": self.status,
            "error": self.error,
        }


def _read_run(paths: WorksPaths, run_file: Path) -> tuple[RunRecord, Evidence, Task]:
    record = RunRecord.model_validate_json(run_file.read_text(encoding="utf-8"))
    run_dir = run_file.parent
    evidence_path = run_dir / "evidence.json"
    if not evidence_path.exists():
        raise FileNotFoundError(f"{run_dir.name} has no evidence.json")
    evidence = Evidence.model_validate_json(evidence_path.read_text(encoding="utf-8"))
    if not evidence.proof_sha256:
        evidence = evidence.bind()
    task = Queue(paths).load(record.task_id)
    return record, evidence, task


def _append_memory_event(
    paths: WorksPaths,
    task_id: str,
    kind: str,
    run_id: str,
    **data: str,
) -> None:
    queue = Queue(paths)
    if any(
        event.type == kind and event.data.get("run_id") == run_id for event in queue.events(task_id)
    ):
        return
    queue.append(task_id, kind, {"run_id": run_id, **data})


def backfill_runs(
    paths: WorksPaths,
    memory: Memory,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    task_id: str | None = None,
    since: datetime | None = None,
) -> list[BackfillEntry]:
    """Report every readable finished run, newest first, and never stop at the first bad one."""
    run_files = sorted(paths.runs.glob("*/run.json"), reverse=True)
    entries: list[BackfillEntry] = []
    for run_file in run_files:
        run_id = run_file.parent.name
        task_id_found = ""
        try:
            record, evidence, task = _read_run(paths, run_file)
            task_id_found = record.task_id
            if task_id is not None and record.task_id != task_id:
                continue
            if since is not None and record.finished_at < since:
                continue
            if limit is not None and len(entries) >= max(0, limit):
                break
            if dry_run:
                entries.append(BackfillEntry(run_id, task_id_found, "dry-run"))
                continue
            try:
                memory.record(task=task, record=record, evidence=evidence)
            except Exception as exc:
                _append_memory_event(
                    paths,
                    task_id_found,
                    "memory.failed",
                    record.run_id,
                    error=str(exc)[:500],
                    via="backfill",
                )
                entries.append(BackfillEntry(run_id, task_id_found, "failed", str(exc)))
                continue
            _append_memory_event(
                paths,
                task_id_found,
                "memory.reported",
                record.run_id,
                app="ppma",
                via="backfill",
            )
            entries.append(BackfillEntry(run_id, task_id_found, "reported"))
        except FileNotFoundError:
            entries.append(BackfillEntry(run_id, task_id_found, "skipped", "no evidence.json"))
        except Exception as exc:  # one bad run must not hide the rest
            entries.append(BackfillEntry(run_id, task_id_found, "failed", str(exc)))
    return entries
