"""Leases and the one-dispatcher lock.

The supervisor already owns `owner` while a run is in flight (it claims with the run id). The
scheduler therefore keeps its own lease next to the task: it protects against a second scheduler and
is the basis for slot accounting, without stealing the supervisor's claim.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from filelock import FileLock, Timeout

from works.adapters.queue.atomic import atomic_write
from works.adapters.queue.store import Queue
from works.config.paths import WorksPaths
from works.domain.errors import ConflictError

LEASE_FILE = "scheduler-lease.json"
LOCK_FILE = "dispatcher.lock"
DEFAULT_TTL_S = 900


@dataclass(frozen=True)
class Lease:
    task_id: str
    owner: str
    claimed_at: datetime
    expires_at: datetime
    estimated_min: float = 0.0

    def active(self, now: datetime) -> bool:
        return self.expires_at > now


def lease_path(paths: WorksPaths, task_id: str) -> Path:
    return paths.task_dir(task_id) / LEASE_FILE


def _parse(raw: str) -> Lease | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        claimed = datetime.fromisoformat(str(payload["claimed_at"]))
        expires = datetime.fromisoformat(str(payload["expires_at"]))
        return Lease(
            task_id=str(payload["task_id"]),
            owner=str(payload["owner"]),
            claimed_at=claimed,
            expires_at=expires,
            estimated_min=float(payload.get("estimated_min") or 0.0),
        )
    except (KeyError, TypeError, ValueError):
        return None


def read_lease(paths: WorksPaths, task_id: str) -> Lease | None:
    path = lease_path(paths, task_id)
    if not path.exists():
        return None
    return _parse(path.read_text(encoding="utf-8"))


def claim(
    paths: WorksPaths,
    task_id: str,
    *,
    owner: str,
    ttl_seconds: int = DEFAULT_TTL_S,
    estimated_min: float = 0.0,
    now: datetime | None = None,
) -> Lease:
    """Take the lease atomically enough for one local dispatcher."""
    moment = now or datetime.now(tz=UTC)
    current = read_lease(paths, task_id)
    if current is not None and current.active(moment) and current.owner != owner:
        raise ConflictError(f"task {task_id} is leased by {current.owner}")
    lease = Lease(
        task_id=task_id,
        owner=owner,
        claimed_at=moment,
        expires_at=moment + timedelta(seconds=ttl_seconds),
        estimated_min=estimated_min,
    )
    path = lease_path(paths, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(
        path,
        json.dumps(
            {
                "task_id": lease.task_id,
                "owner": lease.owner,
                "claimed_at": lease.claimed_at.isoformat(),
                "expires_at": lease.expires_at.isoformat(),
                "estimated_min": lease.estimated_min,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )
    return lease


def release(paths: WorksPaths, task_id: str, *, owner: str) -> None:
    path = lease_path(paths, task_id)
    current = read_lease(paths, task_id)
    if current is not None and current.owner == owner and path.exists():
        path.unlink()


def active_leases(paths: WorksPaths, now: datetime | None = None) -> list[Lease]:
    moment = now or datetime.now(tz=UTC)
    leases: list[Lease] = []
    if not paths.queue.exists():
        return leases
    for path in paths.queue.glob(f"*/{LEASE_FILE}"):
        try:
            lease = _parse(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if lease is not None and lease.active(moment):
            leases.append(lease)
    return leases


def reclaim_stale(paths: WorksPaths, queue: Queue, now: datetime | None = None) -> list[str]:
    """Remove expired leases and say so in the task history; a crashed dispatcher must not wedge."""
    moment = now or datetime.now(tz=UTC)
    reclaimed: list[str] = []
    if not paths.queue.exists():
        return reclaimed
    for path in paths.queue.glob(f"*/{LEASE_FILE}"):
        try:
            lease = _parse(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if lease is None or lease.active(moment):
            continue
        path.unlink(missing_ok=True)
        if queue.exists(lease.task_id):
            queue.append(
                lease.task_id,
                "scheduler.reclaimed",
                {"owner": lease.owner, "expired_at": lease.expires_at.isoformat()},
            )
        reclaimed.append(lease.task_id)
    return reclaimed


def dispatcher_lock_path(paths: WorksPaths) -> Path:
    return paths.state / LOCK_FILE


@contextmanager
def dispatcher(paths: WorksPaths) -> Iterator[bool]:
    """Yield True when this process owns the dispatcher lock, False when another one does."""
    paths.state.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(dispatcher_lock_path(paths)), timeout=0)
    try:
        lock.acquire()
    except Timeout:
        yield False
        return
    try:
        yield True
    finally:
        lock.release()
