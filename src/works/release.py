"""A release packet is the last read-only check before a human release.

It does not publish. It binds the task to the latest run, the exact commit and the proof, and lists
what still blocks a release. A publisher adapter can consume the packet later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import WorksPaths
from .evidence import Evidence
from .queue import Queue
from .records import RunRecord, TaskState


@dataclass
class ReleasePacket:
    task_id: str
    run_id: str | None = None
    commit: str | None = None
    proof_sha256: str | None = None
    plan_gate: dict[str, Any] | None = None
    release_gate: dict[str, Any] | None = None
    blockers: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.blockers

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "commit": self.commit,
            "proof_sha256": self.proof_sha256,
            "plan_gate": self.plan_gate,
            "release_gate": self.release_gate,
            "ready": self.ready,
            "blockers": self.blockers,
        }


def _latest_run(paths: WorksPaths, task_id: str) -> Path | None:
    latest: tuple[str, Path] | None = None
    for run_file in paths.runs.glob("*/run.json"):
        try:
            data = json.loads(run_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("task_id") != task_id:
            continue
        finished = str(data.get("finished_at", ""))
        if latest is None or finished >= latest[0]:
            latest = (finished, run_file.parent)
    return latest[1] if latest is not None else None


def release_packet(paths: WorksPaths, task_id: str) -> ReleasePacket:
    queue = Queue(paths)
    task = queue.load(task_id)
    packet = ReleasePacket(task_id=task_id)
    if task.state is not TaskState.PROVED:
        packet.blockers.append(f"task is {task.state.value}, not proved")
    for event in queue.events(task_id):
        if event.type != "gate.decided":
            continue
        if event.data.get("gate") == "plan":
            packet.plan_gate = dict(event.data)
        elif event.data.get("gate") == "release":
            packet.release_gate = dict(event.data)
    if packet.plan_gate is None:
        packet.blockers.append("plan gate has no human approval")
    if packet.release_gate is None:
        packet.blockers.append("release gate has no human approval")

    run_dir = _latest_run(paths, task_id)
    if run_dir is None:
        packet.blockers.append("no finished run")
        return packet
    try:
        record = RunRecord.model_validate_json((run_dir / "run.json").read_text(encoding="utf-8"))
        evidence = Evidence.model_validate_json(
            (run_dir / "evidence.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        packet.blockers.append(f"cannot read proof: {exc}")
        return packet
    packet.run_id = record.run_id
    packet.commit = record.base_commit
    packet.proof_sha256 = evidence.proof_sha256 or None
    if not packet.proof_sha256:
        packet.blockers.append("proof is unbound")
    if evidence.verdict is None or not evidence.verdict.allow:
        packet.blockers.append("verdict is not allow")
    if evidence.challenge is not None and not evidence.challenge.allow:
        packet.blockers.append("independent review blocked")
    if packet.plan_gate and packet.plan_gate.get("commit") != packet.commit:
        packet.blockers.append("plan approval is bound to another commit")
    return packet
