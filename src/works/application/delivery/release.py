"""A release packet is the last read-only check before a human release.

It does not publish. It binds the task to the latest run, the exact commit and the proof, and lists
what still blocks a release. A publisher adapter can consume the packet later.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from works.adapters.queue.store import Queue
from works.application.approvals.gates import check_actor, quorum_required
from works.application.proof.verify import verify_run
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError
from works.domain.evidence import Evidence
from works.domain.records import RunRecord, Task, TaskState
from works.domain.state import can_transition

TTL_ENV = "WORKS_RELEASE_TTL_HOURS"
OWNER_ENV = "WORKS_REQUIRE_OWNER_APPROVAL"
HIGH_RISK = {"high", "critical"}
DEFAULT_TTL_HOURS = 72
RELEASE_DECISIONS = frozenset({"approved", "changes_requested", "rejected"})


@dataclass
class ReleasePacket:
    task_id: str
    run_id: str | None = None
    commit: str | None = None
    proof_sha256: str | None = None
    plan_gate: dict[str, Any] | None = None
    release_gate: dict[str, Any] | None = None
    blockers: list[str] = field(default_factory=list)
    blocker_codes: list[dict[str, str]] = field(default_factory=list)
    risk: str | None = None
    risk_reasons: list[str] = field(default_factory=list)
    risk_files: int = 0
    risk_lines: int = 0
    owners: list[str] = field(default_factory=list)
    not_tested: list[str] = field(default_factory=list)
    verdict_allow: bool | None = None
    challenge_allow: bool | None = None
    tokens: int = 0
    usd: float = 0.0
    estimated_tokens: int = 0
    estimated_usd: float = 0.0
    proof_verified: bool = False
    delivery_configured: bool = False
    rollback: str = "discard the worktree; delivery never rewrites history"

    @property
    def ready(self) -> bool:
        return not self.blockers

    @property
    def released(self) -> bool:
        return self.release_gate is not None and self.release_gate.get("decision") == "approved"

    def block(self, code: str, detail: str) -> None:
        self.blockers.append(detail)
        self.blocker_codes.append({"code": code, "detail": detail})

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
            "blocker_codes": self.blocker_codes,
            "risk": self.risk,
            "risk_reasons": self.risk_reasons,
            "risk_files": self.risk_files,
            "risk_lines": self.risk_lines,
            "owners": self.owners,
            "not_tested": self.not_tested,
            "verdict_allow": self.verdict_allow,
            "challenge_allow": self.challenge_allow,
            "tokens": self.tokens,
            "usd": self.usd,
            "estimated_tokens": self.estimated_tokens,
            "estimated_usd": self.estimated_usd,
            "proof_verified": self.proof_verified,
            "delivery_configured": self.delivery_configured,
            "rollback": self.rollback,
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


def ttl_hours() -> int:
    raw = os.environ.get(TTL_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_TTL_HOURS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{TTL_ENV} must be a whole number of hours") from exc
    if value <= 0:
        raise ConfigError(f"{TTL_ENV} must be positive")
    return value


def owner_approval_required() -> bool:
    return os.environ.get(OWNER_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def owner_approved(risk: str | None, owners: list[str], actor: str) -> bool:
    if not owner_approval_required():
        return True
    if (risk or "low").lower() not in HIGH_RISK:
        return True
    return not owners or actor in owners


def _expired(gate: dict[str, Any] | None) -> bool:
    raw = str((gate or {}).get("expires_at") or "")
    if not raw:
        return False
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return True
    return moment <= datetime.now(tz=UTC)


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
        packet.block("not_proved", f"task is {task.state.value}, not proved")
    for event in queue.events(task_id):
        if event.type != "gate.decided":
            continue
        if event.data.get("gate") == "plan":
            packet.plan_gate = dict(event.data)
        elif event.data.get("gate") == "release":
            packet.release_gate = dict(event.data)
    if packet.plan_gate is None:
        packet.block("plan_gate_missing", "plan gate has no human approval")
    if require_release_gate and packet.release_gate is None:
        packet.block("release_gate_missing", "release gate has no human approval")

    run_dir = _latest_run(paths, task_id)
    if run_dir is None:
        packet.block("no_run", "no finished run")
        return packet
    try:
        record = RunRecord.model_validate_json((run_dir / "run.json").read_text(encoding="utf-8"))
        evidence = Evidence.model_validate_json(
            (run_dir / "evidence.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        packet.block("unreadable_proof", f"cannot read proof: {exc}")
        return packet
    packet.run_id = record.run_id
    packet.commit = record.base_commit
    packet.proof_sha256 = evidence.proof_sha256 or None
    packet.risk = evidence.risk.level.value if evidence.risk else None
    packet.risk_reasons = list(evidence.risk.reasons) if evidence.risk else []
    packet.risk_files = evidence.risk.files if evidence.risk else 0
    packet.risk_lines = evidence.risk.lines if evidence.risk else 0
    packet.owners = list(evidence.risk.owners) if evidence.risk else []
    packet.not_tested = list(evidence.not_tested)
    packet.verdict_allow = evidence.verdict.allow if evidence.verdict else None
    packet.challenge_allow = evidence.challenge.allow if evidence.challenge else None
    packet.tokens = evidence.tokens
    packet.usd = evidence.usd
    packet.estimated_tokens = evidence.plan_estimated_tokens
    packet.estimated_usd = evidence.plan_estimated_usd
    checked = verify_run(paths, record.run_id)
    packet.proof_verified = checked.ok
    if not checked.ok:
        failed = ", ".join(check.name for check in checked.checks if not check.ok)
        packet.block("proof_mismatch", f"proof does not verify: {failed}")
    if not packet.proof_sha256:
        packet.block("proof_unbound", "proof is unbound")
    if evidence.verdict is None or not evidence.verdict.allow:
        packet.block("must_pass_failed", "verdict is not allow")
    if evidence.challenge is not None and not evidence.challenge.allow:
        packet.block("challenge_blocked", "independent review blocked")
    if evidence.policy is not None and not evidence.policy.ok:
        packet.block("policy_violation", "the policy report is not clean")
    if packet.plan_gate and packet.plan_gate.get("commit") != packet.commit:
        packet.block("stale_plan", "plan approval is bound to another commit")
    if packet.release_gate:
        if packet.release_gate.get("commit") != packet.commit:
            packet.block("stale_release", "release approval is bound to another commit")
        if packet.release_gate.get("proof_sha256") != packet.proof_sha256:
            packet.block("stale_release", "release approval is bound to another proof")
        if _expired(packet.release_gate):
            packet.block("expired_release", "release approval has expired")
    try:
        repo = Path(task.repo)
        packet.delivery_configured = bool(task.repo) and (repo / ".git").exists()
    except OSError:
        packet.delivery_configured = False
    return packet


def decide_release(
    paths: WorksPaths,
    task_id: str,
    *,
    decision: str = "approved",
    by: str = "person",
    device: str = "local",
    comment: str = "",
    actor_kind: str = "person",
) -> tuple[Task, ReleasePacket, bool]:
    if decision not in RELEASE_DECISIONS:
        raise ConfigError(f"unknown release decision {decision!r}")
    actor = check_actor(by, actor_kind)
    note = comment.strip()
    if decision in ("changes_requested", "rejected") and not note:
        raise ConfigError(f"{decision} needs a comment explaining why")
    queue = Queue(paths)
    task = queue.load(task_id)
    packet = release_packet(paths, task_id, require_release_gate=False)
    if decision == "approved" and not packet.ready:
        raise ConfigError("release is blocked: " + "; ".join(packet.blockers))
    if decision == "approved" and not owner_approved(packet.risk, packet.owners, actor):
        raise ConfigError(
            f"high-risk release needs an owner approval; owners: {', '.join(packet.owners)}"
        )
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

    packet_hash = hashlib.sha256(
        json.dumps(packet.as_dict(), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    audit = {
        "gate": "release",
        "decision": decision,
        "by": actor,
        "device": device.strip() or "local",
        "actor_kind": actor_kind,
        "comment": note,
        "commit": packet.commit,
        "proof_sha256": packet.proof_sha256,
        "run_id": packet.run_id,
        "packet_hash": packet_hash,
    }

    if decision == "approved":
        if quorum_required():
            prior = [
                event
                for event in queue.events(task_id)
                if event.type == "gate.approval"
                and event.data.get("gate") == "release"
                and event.data.get("proof_sha256") == packet.proof_sha256
            ]
            if any(
                event.data.get("by") == actor and event.data.get("device") == audit["device"]
                for event in prior
            ):
                raise ConfigError("the same person on the same device cannot satisfy a quorum")
            if not prior:
                queue.append(
                    task_id,
                    "gate.approval",
                    {**audit, "expires_at": _expires(), "note": "waiting for a second approver"},
                )
                return queue.load(task_id), release_packet(paths, task_id), False
        if not can_transition(task.state, TaskState.RELEASING) or not can_transition(
            TaskState.RELEASING, TaskState.RELEASED
        ):
            raise ConfigError(f"task {task_id} is {task.state.value}; it cannot be released")
        released_at = datetime.now(tz=UTC).isoformat()
        queue.transition(task_id, TaskState.RELEASING, reason="release approved")
        queue.transition(task_id, TaskState.RELEASED, reason="release approved")
        event = queue.append(
            task_id,
            "gate.decided",
            {
                **audit,
                "released_at": released_at,
                "expires_at": _expires(),
                "quorum": quorum_required(),
            },
        )
        run_dir = _latest_run(paths, task_id)
        if run_dir is not None:
            (run_dir / "release.json").write_text(
                json.dumps(
                    {
                        **audit,
                        "released_at": released_at,
                        "expires_at": event.data["expires_at"],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        return queue.load(task_id), release_packet(paths, task_id), True

    if decision == "changes_requested":
        event = queue.append(task_id, "gate.decided", audit)
        return queue.load(task_id), release_packet(paths, task_id), False

    if task.state is not TaskState.BLOCKED:
        queue.transition(task_id, TaskState.BLOCKED, reason="release rejected")
    event = queue.append(task_id, "gate.decided", audit)
    return queue.load(task_id), release_packet(paths, task_id), False


def _expires() -> str:
    return (datetime.now(tz=UTC) + timedelta(hours=ttl_hours())).isoformat()


def approve_release(
    paths: WorksPaths, task_id: str, *, by: str = "cli"
) -> tuple[Task, ReleasePacket, bool]:
    return decide_release(paths, task_id, decision="approved", by=by)
