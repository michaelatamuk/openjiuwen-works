"""Watch a released change: re-run its confirmation and file a task when it stops passing.

The baseline is the confirmation recorded when the change was released. A later re-check that fails
after a passing baseline is a drift; it becomes one task with the previous run and proof in its
reproduction hint. The monitor never approves or releases anything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from works.adapters.queue.atomic import atomic_write
from works.adapters.queue.store import Queue
from works.application.delivery.confirm import Confirmation, confirm
from works.application.delivery.release import latest_run_dir
from works.config.paths import WorksPaths
from works.domain.enums import SourceKind, TaskState
from works.domain.errors import WorksError
from works.domain.task import Source, Task

STATE_DIR = "monitor"


class ConfirmFn(Protocol):
    def __call__(
        self,
        paths: WorksPaths,
        task_id: str,
        *,
        url: str | None = None,
        command: list[str] | None = None,
        force: bool = False,
        record: bool = True,
    ) -> Confirmation: ...


@dataclass(frozen=True)
class DriftCheck:
    task_id: str
    target: str
    baseline_ok: bool
    now_ok: bool
    code: str
    drifted: bool
    created: str | None = None
    existing: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class MonitorResult:
    days: int
    checked: int = 0
    skipped: dict[str, str] = field(default_factory=dict)
    checks: list[DriftCheck] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)


def _state_path(paths: WorksPaths, task_id: str) -> Path:
    return paths.state / STATE_DIR / f"{task_id}.json"


def _load_state(paths: WorksPaths, task_id: str) -> dict[str, object] | None:
    try:
        raw: object = json.loads(_state_path(paths, task_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _confirmation(run_dir: Path | None) -> dict[str, object] | None:
    if run_dir is None:
        return None
    try:
        raw: object = json.loads((run_dir / "confirmation.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _save_state(paths: WorksPaths, task_id: str, payload: dict[str, object]) -> None:
    path = _state_path(paths, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _source(task: Task, check: dict[str, object], now: Confirmation, target: str) -> Source:
    raw_baseline = check.get("baseline")
    baseline = raw_baseline if isinstance(raw_baseline, dict) else {}
    hint = (
        f"`{target}` passed for {task.id} (run {baseline.get('run_id') or '-'}, "
        f"proof {str(baseline.get('proof_sha256') or '-')[:12]}) and now fails with "
        f"{now.code or 'a failed check'}. Re-run it on the repository."
    )
    return Source(
        kind=SourceKind.DETECTOR,
        ref=f"drift:{task.id}",
        title=f"drift: {task.source.title or task.id}",
        severity="S2",
        labels=["drift", f"previous:{task.id}"],
        links=list(task.source.links),
        author="monitor",
        channel="drift",
        reproduction_hint=hint,
        dedupe_key=f"drift:{task.id}:{now.code or 'failed'}:{now.output_sha256[:8]}",
    )


def monitor(
    paths: WorksPaths,
    *,
    days: int = 30,
    dry_run: bool = False,
    confirm_fn: ConfirmFn | None = None,
    queue: Queue | None = None,
    now: datetime | None = None,
) -> MonitorResult:
    check_one = confirm_fn or confirm
    moment = now or datetime.now(tz=UTC)
    cutoff = moment - timedelta(days=days)
    queue = queue or Queue(paths)
    skipped: dict[str, str] = {}
    checks: list[DriftCheck] = []
    created: list[str] = []
    existing: list[str] = []
    checked = 0
    for task in queue.list_tasks():
        if task.state is not TaskState.RELEASED:
            continue
        if task.updated_at < cutoff:
            continue
        run_dir = latest_run_dir(paths, task.id)
        recorded = _confirmation(run_dir)
        if recorded is None:
            skipped[task.id] = "no_confirmation"
            continue
        target = str(recorded.get("target") or "")
        url = recorded.get("url")
        command = recorded.get("command")
        state = _load_state(paths, task.id)
        if state is None:
            baseline = {
                "ok": bool(recorded.get("ok")),
                "code": str(recorded.get("code") or ""),
                "output_sha256": str(recorded.get("output_sha256") or ""),
                "at": recorded.get("at"),
                "run_id": recorded.get("run_id"),
                "proof_sha256": _proof(run_dir),
            }
            state = {
                "schema_version": 1,
                "task_id": task.id,
                "target": target,
                "baseline": baseline,
            }
            if not dry_run:
                _save_state(paths, task.id, state)
        raw_baseline = state.get("baseline")
        baseline = raw_baseline if isinstance(raw_baseline, dict) else {}
        try:
            current = check_one(
                paths,
                task.id,
                url=str(url) if url else None,
                command=command if isinstance(command, list) else None,
                force=True,
                record=not dry_run,
            )
        except (WorksError, OSError, ValueError) as exc:
            skipped[task.id] = f"check_failed: {exc}"
            continue
        checked += 1
        drifted = bool(baseline.get("ok")) and not current.ok
        drift_check = DriftCheck(
            task_id=task.id,
            target=target,
            baseline_ok=bool(baseline.get("ok")),
            now_ok=current.ok,
            code=current.code,
            drifted=drifted,
        )
        if drifted and not dry_run:
            new_task, is_new = queue.submit(
                source=_source(task, state, current, target),
                flow="fix-issue",
                product=task.product,
                repo=task.repo,
            )
            drift_check = replace(
                drift_check,
                created=new_task.id if is_new else None,
                existing=None if is_new else new_task.id,
            )
            (created if is_new else existing).append(new_task.id)
        checks.append(drift_check)
        if not dry_run:
            state["last"] = {
                "ok": current.ok,
                "code": current.code,
                "output_sha256": current.output_sha256,
                "at": current.at,
                "run_id": current.run_id,
            }
            _save_state(paths, task.id, state)
    return MonitorResult(
        days=days,
        checked=checked,
        skipped=skipped,
        checks=checks,
        created=created,
        existing=existing,
    )


def _proof(run_dir: Path | None) -> str:
    if run_dir is None:
        return ""
    try:
        payload = json.loads((run_dir / "evidence.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("proof_sha256") or "")
