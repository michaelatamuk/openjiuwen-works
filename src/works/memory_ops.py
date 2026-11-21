"""Backfill finished runs into PPMA without re-running the factory.

The live supervisor reports a run when it finishes. This module is the recovery path for runs
created before PPMA was configured, for demo workspaces and for a PPMA outage: every run already
has `run.json` and `evidence.json`, so the same idempotent `works.run_finished` event can be sent
later.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def backfill_runs(
    paths: WorksPaths,
    memory: Memory,
    *,
    limit: int | None = None,
    dry_run: bool = False,
) -> list[BackfillEntry]:
    """Report every readable finished run, newest first, and never stop at the first bad one."""
    run_files = sorted(paths.runs.glob("*/run.json"), reverse=True)
    if limit is not None:
        run_files = run_files[: max(0, limit)]
    entries: list[BackfillEntry] = []
    for run_file in run_files:
        run_id = run_file.parent.name
        task_id = ""
        try:
            record, evidence, task = _read_run(paths, run_file)
            task_id = record.task_id
            if dry_run:
                entries.append(BackfillEntry(run_id, task_id, "dry-run"))
                continue
            memory.record(task=task, record=record, evidence=evidence)
            entries.append(BackfillEntry(run_id, task_id, "reported"))
        except FileNotFoundError:
            entries.append(BackfillEntry(run_id, task_id, "skipped", "no evidence.json"))
        except Exception as exc:  # one bad run must not hide the rest
            entries.append(BackfillEntry(run_id, task_id, "failed", str(exc)))
    return entries
