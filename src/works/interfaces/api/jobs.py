"""Background jobs for long actions: status, cancellation and crash reconciliation."""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from works.adapters.processes.runner import CURRENT_CANCEL
from works.adapters.queue.atomic import atomic_write
from works.adapters.queue.store import Queue
from works.config.paths import WorksPaths
from works.domain.errors import ConflictError, NotFoundError

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
FINAL = frozenset({"succeeded", "failed", "cancelled"})
LOG = logging.getLogger("works.jobs")


class JobCancelled(Exception):
    """Raised by a job body that noticed the cancel flag."""


@dataclass
class JobContext:
    job_id: str
    cancel_event: threading.Event

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def check(self) -> None:
        if self.cancelled:
            raise JobCancelled(self.job_id)


@dataclass
class Job:
    id: str
    action: str
    task_id: str | None = None
    status: JobStatus = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: Any = None
    error: str | None = None
    error_code: str | None = None
    log_tail: str = ""
    cancelable: bool = True
    timeout_s: float | None = None
    trace_id: str = field(default_factory=lambda: secrets.token_hex(8))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobRunner:
    def __init__(self, paths: WorksPaths, queue: Queue, *, max_workers: int = 2) -> None:
        self._directory = paths.state / "jobs"
        self._directory.mkdir(parents=True, exist_ok=True)
        self._queue = queue
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="works-job")
        self._jobs: dict[str, Job] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._timers: dict[str, threading.Timer] = {}
        self._locks: dict[str, str] = {}
        self._guard = threading.RLock()
        self.reconcile()

    def _path(self, job_id: str) -> Path:
        return self._directory / f"{job_id}.json"

    def _persist(self, job: Job) -> None:
        atomic_write(
            self._path(job.id),
            json.dumps(job.as_dict(), ensure_ascii=False, default=str) + "\n",
        )

    def get(self, job_id: str) -> Job:
        with self._guard:
            job = self._jobs.get(job_id)
            if job is None:
                raise NotFoundError(f"job not found: {job_id}")
            return job

    def submit(
        self,
        action: str,
        body: Callable[[JobContext], Any],
        *,
        task_id: str | None = None,
        timeout_s: float | None = None,
    ) -> Job:
        if timeout_s is None:
            raw = os.environ.get("WORKS_JOB_TIMEOUT")
            timeout_s = float(raw) if raw else None
        with self._guard:
            if task_id is not None and task_id in self._locks:
                raise ConflictError(f"task {task_id} already has a running job")
            job = Job(
                id=f"j-{secrets.token_hex(6)}",
                action=action,
                task_id=task_id,
                timeout_s=timeout_s,
            )
            self._jobs[job.id] = job
            self._cancel[job.id] = threading.Event()
            if task_id is not None:
                self._locks[task_id] = job.id
            self._persist(job)
            if timeout_s is not None and timeout_s > 0:
                timer = threading.Timer(timeout_s, self._expire, args=(job.id,))
                timer.daemon = True
                self._timers[job.id] = timer
        self._executor.submit(self._run, job.id, body)
        pending = self._timers.get(job.id)
        if pending is not None:
            pending.start()
        return job

    def _expire(self, job_id: str) -> None:
        with self._guard:
            job = self._jobs.get(job_id)
            if job is None or job.status in FINAL:
                return
            self._cancel[job_id].set()
            job.error_code = "timeout"
            job.error = f"job timed out after {job.timeout_s or 0:.1f}s"
            job.log_tail = job.error
            self._finish(job, "failed")

    def _run(self, job_id: str, body: Callable[[JobContext], Any]) -> None:
        with self._guard:
            job = self._jobs[job_id]
            event = self._cancel[job_id]
            if event.is_set() or job.status in FINAL:
                self._finish(job, "cancelled")
                return
            job.status = "running"
            job.started_at = time.time()
            self._persist(job)
            LOG.info(
                "job started",
                extra={"job_id": job.id, "task_id": job.task_id, "action": job.action},
            )
        token = CURRENT_CANCEL.set(event)
        try:
            result = body(JobContext(job_id=job_id, cancel_event=event))
        except JobCancelled:
            self._finish(job, "cancelled")
        except Exception as exc:  # a job failure is a status, not a crash
            with self._guard:
                job.error = f"{type(exc).__name__}: {exc}"[:1000]
                job.error_code = getattr(exc, "code", None)
                job.log_tail = job.error
            self._finish(job, "failed")
        else:
            with self._guard:
                job.result = result
            self._finish(job, "cancelled" if event.is_set() else "succeeded")
        finally:
            CURRENT_CANCEL.reset(token)

    def _finish(self, job: Job, status: JobStatus) -> None:
        with self._guard:
            if job.status in FINAL:
                return
            timer = self._timers.pop(job.id, None)
            if timer is not None:
                timer.cancel()
            job.status = status
            job.finished_at = time.time()
            job.cancelable = False
            if job.task_id is not None:
                self._locks.pop(job.task_id, None)
            self._persist(job)
            started = job.started_at or job.created_at
            LOG.info(
                "job finished",
                extra={
                    "job_id": job.id,
                    "task_id": job.task_id,
                    "action": job.action,
                    "status": status,
                    "trace_id": job.trace_id,
                    "duration_ms": int((time.time() - started) * 1000),
                },
            )

    def cancel(self, job_id: str) -> Job:
        with self._guard:
            job = self._jobs.get(job_id)
            if job is None:
                raise NotFoundError(f"job not found: {job_id}")
            if job.status in FINAL:
                return job
            self._cancel[job_id].set()
            timer = self._timers.pop(job.id, None)
            if timer is not None:
                timer.cancel()
            if job.status == "queued":
                self._finish(job, "cancelled")
            return job

    def reconcile(self) -> None:
        """Load persisted jobs and fail anything the previous daemon left running."""
        for path in self._directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            try:
                job = Job(**payload)
            except TypeError:
                continue
            with self._guard:
                self._jobs[job.id] = job
                self._cancel.setdefault(job.id, threading.Event())
                stale = job.status in ("queued", "running")
                if stale:
                    job.status = "failed"
                    job.error = "daemon restarted while the job was running"
                    job.finished_at = time.time()
                    job.cancelable = False
                    self._persist(job)
                if stale and job.task_id is not None:
                    try:
                        owner = self._queue.owner(job.task_id)
                        if owner:
                            self._queue.release(job.task_id, owner)
                    except NotFoundError:
                        pass

    def metrics(self) -> dict[str, int]:
        with self._guard:
            counts: dict[str, int] = dict.fromkeys(
                ("queued", "running", "succeeded", "failed", "cancelled"), 0
            )
            for job in self._jobs.values():
                counts[job.status] = counts.get(job.status, 0) + 1
            return counts

    def shutdown(self) -> None:
        with self._guard:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
        self._executor.shutdown(wait=False, cancel_futures=True)
