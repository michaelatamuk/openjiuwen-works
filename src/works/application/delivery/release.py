"""A release packet is the last read-only check before a human release.

It does not publish. It binds the task to the latest run, the exact commit and the proof, and lists
what still blocks a release. A publisher adapter can consume the packet later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from works.adapters.queue.store import Queue
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError
from works.domain.evidence import Evidence
from works.domain.records import RunRecord, Task, TaskState
from works.domain.state import can_transition


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

    @property
    def released(self) -> bool:
        return self.release_gate is not None and self.release_gate.get("decision") == "approved"

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "commit": self.commit,
            "proof_sha256": self.proof_sha256,
            "plan_gate": self.plan_gate,
            "release_gate": self.release_gate,
            "ready": self.ready,
            "released": self.released,
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


def latest_run_dir(paths: WorksPaths, task_id: str) -> Path | None:
    return _latest_run(paths, task_id)


def release_packet(
    paths: WorksPaths, task_id: str, *, require_release_gate: bool = True
) -> ReleasePacket:
    queue = Queue(paths)
    task = queue.load(task_id)
    packet = ReleasePacket(task_id=task_id)
    releasable = {
        TaskState.PROVED,
        TaskState.WAITING_REVIEW,
        TaskState.WAITING_CI,
        TaskState.WAITING_DEPLOY,
        TaskState.RELEASED,
    }
    if task.state not in releasable:
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
    if require_release_gate and packet.release_gate is None:
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
    if packet.release_gate:
        if packet.release_gate.get("commit") != packet.commit:
            packet.blockers.append("release approval is bound to another commit")
        if packet.release_gate.get("proof_sha256") != packet.proof_sha256:
            packet.blockers.append("release approval is bound to another proof")
    return packet


def approve_release(
    paths: WorksPaths, task_id: str, *, by: str = "cli"
) -> tuple[Task, ReleasePacket, bool]:
    """Open gate 2: a person releases the approved commit. Nothing is published here.

    Returns `(task, packet, created)`. A repeat approval for the same commit is idempotent and
    returns `created=False`.
    """
    queue = Queue(paths)
    task = queue.load(task_id)
    packet = release_packet(paths, task_id, require_release_gate=False)
    if not packet.ready:
        raise ConfigError("release is blocked: " + "; ".join(packet.blockers))
    if packet.commit is None:
        raise ConfigError("the release packet names no commit")
    if task.state is TaskState.RELEASED:
        gate = packet.release_gate or {}
        if gate.get("commit") == packet.commit and gate.get("proof_sha256") == packet.proof_sha256:
            return task, release_packet(paths, task_id), False
        raise ConfigError(
            f"task {task_id} was already released at {gate.get('commit')}; "
            "a new change needs a new run"
        )
    if not can_transition(task.state, TaskState.RELEASING) or not can_transition(
        TaskState.RELEASING, TaskState.RELEASED
    ):
        raise ConfigError(f"task {task_id} is {task.state.value}; it cannot be released")
    released_at = datetime.now(tz=UTC).isoformat()
    queue.transition(task_id, TaskState.RELEASING, reason="release approved")
    queue.transition(task_id, TaskState.RELEASED, reason="release approved")
    queue.append(
        task_id,
        "gate.decided",
        {
            "gate": "release",
            "decision": "approved",
            "by": by,
            "commit": packet.commit,
            "proof_sha256": packet.proof_sha256,
            "run_id": packet.run_id,
            "released_at": released_at,
        },
    )
    run_dir = _latest_run(paths, task_id)
    if run_dir is not None:
        (run_dir / "release.json").write_text(
            json.dumps(
                {
                    "task_id": task_id,
                    "run_id": packet.run_id,
                    "commit": packet.commit,
                    "proof_sha256": packet.proof_sha256,
                    "by": by,
                    "released_at": released_at,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return queue.load(task_id), release_packet(paths, task_id), True
