from __future__ import annotations

import subprocess
import sys
import textwrap
from datetime import UTC, datetime, timedelta

import pytest

from works.adapters.queue.store import Queue
from works.application.scheduling import lease
from works.application.scheduling.loop import Scheduler
from works.domain.errors import ConflictError
from works.domain.records import Source, SourceKind

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


def _task(paths, ref: str = "R") -> str:
    task, _created = Queue(paths).submit(
        source=Source(kind=SourceKind.MANUAL, ref=ref, title="t"),
        flow="fix-issue",
        product="P",
        repo=str(paths.root / "repo"),
    )
    return task.id


def test_a_claim_is_visible_and_released(paths) -> None:
    task_id = _task(paths)

    lease.claim(paths, task_id, owner="scheduler:a", ttl_seconds=60, now=NOW)

    active = lease.active_leases(paths, NOW)
    assert [item.task_id for item in active] == [task_id]
    assert lease.read_lease(paths, task_id) is not None

    lease.release(paths, task_id, owner="scheduler:a")

    assert lease.active_leases(paths, NOW) == []
    assert lease.read_lease(paths, task_id) is None


def test_a_second_owner_is_refused(paths) -> None:
    task_id = _task(paths)
    lease.claim(paths, task_id, owner="scheduler:a", ttl_seconds=60, now=NOW)

    with pytest.raises(ConflictError, match="leased by"):
        lease.claim(paths, task_id, owner="scheduler:b", ttl_seconds=60, now=NOW)


def test_an_expired_lease_is_reclaimed_with_an_event(paths) -> None:
    task_id = _task(paths)
    lease.claim(paths, task_id, owner="scheduler:a", ttl_seconds=60, now=NOW)

    reclaimed = lease.reclaim_stale(paths, Queue(paths), NOW + timedelta(minutes=5))

    assert reclaimed == [task_id]
    assert lease.read_lease(paths, task_id) is None
    events = [item for item in Queue(paths).events(task_id) if item.type == "scheduler.reclaimed"]
    assert len(events) == 1


def test_a_live_lease_is_not_reclaimed(paths) -> None:
    task_id = _task(paths)
    lease.claim(paths, task_id, owner="scheduler:a", ttl_seconds=60, now=NOW)

    assert lease.reclaim_stale(paths, Queue(paths), NOW + timedelta(seconds=30)) == []


def test_the_dispatcher_lock_is_exclusive_in_one_process(paths) -> None:
    with lease.dispatcher(paths) as held:
        assert held is True
    with lease.dispatcher(paths) as held:
        assert held is True


def test_a_second_process_is_refused(paths) -> None:
    from works.application.scheduling.policy import POLICY_PATH

    path = paths.root / POLICY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("enabled: true\nallow:\n  manual: true\n", encoding="utf-8")
    code = textwrap.dedent(
        f"""
        import time
        from pathlib import Path
        from works.application.scheduling import lease
        from works.config.paths import WorksPaths

        with lease.dispatcher(WorksPaths(Path(r"{paths.root}"))) as held:
            print(held, flush=True)
            time.sleep(20)
        """
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "True"
        result = Scheduler(paths, now=lambda: NOW).tick()
        assert result.status == "conflict"
    finally:
        holder.terminate()
        holder.wait(timeout=10)


def test_a_corrupt_lease_reads_as_missing(paths) -> None:
    task_id = _task(paths)
    lease.lease_path(paths, task_id).write_text("{broken", encoding="utf-8")

    assert lease.read_lease(paths, task_id) is None


def test_release_ignores_another_owner(paths) -> None:
    task_id = _task(paths)
    lease.claim(paths, task_id, owner="scheduler:a", ttl_seconds=60, now=NOW)

    lease.release(paths, task_id, owner="scheduler:b")

    assert lease.read_lease(paths, task_id) is not None
