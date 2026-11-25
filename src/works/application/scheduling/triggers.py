"""`dispatch_on_import`: an explicit request, never a run.

The request writes `scheduler.requested` and lets the next tick decide. It is refused softly with a
typed reason so an import still returns its task instead of failing halfway.
"""

from __future__ import annotations

from dataclasses import dataclass

from works.adapters.queue.store import Queue
from works.application import limits
from works.application.scheduling.policy import load_policy
from works.application.scheduling.select import source_name
from works.config.paths import WorksPaths
from works.domain.enums import SourceKind


@dataclass(frozen=True)
class TriggerResult:
    requested: bool
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"requested": self.requested, "reason": self.reason}


def remaining_usd(paths: WorksPaths) -> float | None:
    cap = limits.cap()
    if cap is None:
        return None
    return max(0.0, cap - limits.spent(paths))


def request_dispatch(paths: WorksPaths, task_id: str, *, remote: bool) -> TriggerResult:
    policy = load_policy(paths)
    if not policy.enabled:
        return TriggerResult(False, "disabled")
    if remote and not policy.allow.remote_triggers:
        return TriggerResult(False, "remote_trigger")
    queue = Queue(paths)
    task = queue.load(task_id)
    source = source_name(task)
    if task.source.kind is SourceKind.MANUAL:
        if not policy.allow.manual:
            return TriggerResult(False, "manual_not_allowed")
    elif policy.allow.sources and source not in policy.allow.sources:
        return TriggerResult(False, "not_allowlisted")
    if policy.allow.flows and task.flow not in policy.allow.flows:
        return TriggerResult(False, "flow_not_allowed")
    remaining = remaining_usd(paths)
    if remaining is not None and remaining <= 0:
        return TriggerResult(False, "budget_exhausted")
    queue.append(task_id, "scheduler.requested", {"remote": remote, "source": source})
    return TriggerResult(True)
