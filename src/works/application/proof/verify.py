"""Proof integrity: the page, the diff, the artifacts and the event root."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from works.adapters.queue.store import Queue
from works.application.proof.chain import event_root
from works.config.paths import WorksPaths
from works.domain.evidence import Evidence


class Check(BaseModel):
    name: str
    ok: bool
    detail: str = ""


class Verification(BaseModel):
    run_id: str
    ok: bool
    checks: list[Check] = Field(default_factory=list)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_run(paths: WorksPaths, run_id: str) -> Verification:
    run_dir = paths.run_dir(run_id)
    checks: list[Check] = []
    evidence_path = run_dir / "evidence.json"
    if not evidence_path.exists():
        return Verification(
            run_id=run_id,
            ok=False,
            checks=[Check(name="evidence", ok=False, detail="evidence.json is missing")],
        )
    evidence = Evidence.model_validate_json(evidence_path.read_text(encoding="utf-8"))

    diff_hash = hashlib.sha256(evidence.diff.encode("utf-8")).hexdigest()
    checks.append(
        Check(
            name="diff",
            ok=diff_hash == evidence.diff_sha256,
            detail="" if diff_hash == evidence.diff_sha256 else "diff does not match diff_sha256",
        )
    )
    rebound = evidence.bind()
    checks.append(
        Check(
            name="proof",
            ok=rebound.proof_sha256 == evidence.proof_sha256,
            detail="" if rebound.proof_sha256 == evidence.proof_sha256 else "proof hash changed",
        )
    )
    artifacts_ok = True
    for artifact in evidence.artifacts:
        path = run_dir / artifact.path
        if not path.is_file() or _sha(path) != artifact.sha256:
            artifacts_ok = False
            checks.append(
                Check(name=f"artifact:{artifact.path}", ok=False, detail="missing or changed")
            )
    if artifacts_ok:
        checks.append(Check(name="artifacts", ok=True))

    if evidence.event_root and evidence.event_seq:
        events = [
            event
            for event in Queue(paths).events(evidence.task_id)
            if event.seq <= evidence.event_seq
        ]
        checks.append(
            Check(
                name="events",
                ok=event_root(events) == evidence.event_root,
                detail="" if event_root(events) == evidence.event_root else "event chain changed",
            )
        )
    return Verification(run_id=run_id, ok=all(check.ok for check in checks), checks=checks)


def compare(paths: WorksPaths, first: str, second: str) -> dict[str, Any]:
    def load(run_id: str) -> Evidence:
        return Evidence.model_validate_json(
            (paths.run_dir(run_id) / "evidence.json").read_text(encoding="utf-8")
        )

    left, right = load(first), load(second)
    return {
        "first": first,
        "second": second,
        "verdict": [
            left.verdict.allow if left.verdict else None,
            right.verdict.allow if right.verdict else None,
        ],
        "risk": [
            left.risk.level.value if left.risk else None,
            right.risk.level.value if right.risk else None,
        ],
        "tokens": [left.tokens, right.tokens],
        "usd": [left.usd, right.usd],
        "files": sorted(set(left.files_changed) ^ set(right.files_changed)),
        "proof_changed": left.proof_sha256 != right.proof_sha256,
    }


def export(paths: WorksPaths, run_id: str, target: Path) -> Path:
    import tarfile

    run_dir = paths.run_dir(run_id)
    if not (run_dir / "evidence.json").exists():
        raise FileNotFoundError(f"{run_id} has no evidence.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"run_id": run_id, "files": {}}
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name not in {"run.json"}:
            manifest["files"][path.relative_to(run_dir).as_posix()] = _sha(path)
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with tarfile.open(target, "w:gz") as archive:
        archive.add(run_dir, arcname=run_id)
    return target
