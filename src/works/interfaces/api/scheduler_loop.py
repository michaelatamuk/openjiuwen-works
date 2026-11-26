"""Run the scheduler inside the daemon.

The loop itself only selects and claims; this adapter turns each claim into the same run job the
manual path uses, and releases the lease when the job ends (or when submission is refused).
"""

from __future__ import annotations

import logging
import threading

from works.adapters.queue.store import Queue
from works.application.scheduling.lease import release
from works.application.scheduling.loop import TRANSIENT, Scheduler
from works.application.scheduling.policy import load_policy
from works.interfaces.api.jobs import JobContext
from works.interfaces.api.routes.runs import RunOptions, run_task
from works.interfaces.api.wiring import AppState

LOGGER = logging.getLogger(__name__)


def start(state: AppState) -> threading.Event:
    """Start the background loop; the returned event stops it at shutdown."""
    stop = threading.Event()
    thread = threading.Thread(
        target=_run,
        args=(state, stop),
        name="works-scheduler",
        daemon=True,
    )
    thread.start()
    return stop


def _run(state: AppState, stop: threading.Event) -> None:
    scheduler = Scheduler(state.paths)
    while not stop.is_set():
        try:
            policy = load_policy(state.paths)
        except Exception:  # a broken policy must not kill the daemon
            LOGGER.exception("scheduler policy is unreadable")
            if stop.wait(10):
                return
            continue
        if stop.wait(max(1, policy.tick_seconds)):
            return
        if not policy.enabled:
            continue
        try:
            result = scheduler.tick(hold=True)
        except Exception:  # one bad tick must not stop the loop
            LOGGER.exception("scheduler tick failed")
            continue
        for task_id in result.claimed:
            _submit(state, scheduler, task_id)


def _submit(state: AppState, scheduler: Scheduler, task_id: str) -> None:
    options = RunOptions()

    def job(ctx: JobContext) -> dict[str, object]:
        try:
            ctx.check()
            return run_task(state, options, task_id)
        except Exception as exc:
            code = str(getattr(exc, "code", "internal_error"))
            Queue(state.paths).append(
                task_id,
                "scheduler.failed",
                {"code": code, "error": str(exc), "retryable": code in TRANSIENT},
            )
            raise
        finally:
            release(state.paths, task_id, owner=scheduler.owner)

    try:
        state.jobs.submit("run", job, task_id=task_id)
    except Exception:
        LOGGER.exception("cannot submit the claimed task %s", task_id)
        release(state.paths, task_id, owner=scheduler.owner)
