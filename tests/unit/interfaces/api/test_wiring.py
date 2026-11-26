from __future__ import annotations

from works.application.scheduling.policy import POLICY_PATH
from works.interfaces.api.wiring import job_workers


def _policy(paths, slots: int) -> None:
    path = paths.root / POLICY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"enabled: true\nallow:\n  manual: true\nconcurrency:\n  global: {slots}\n  per_repo: 1\n",
        encoding="utf-8",
    )


def test_the_pool_follows_the_global_slots(paths) -> None:
    _policy(paths, 3)

    assert job_workers(paths) == 3


def test_the_pool_is_clamped_to_eight(paths) -> None:
    _policy(paths, 20)

    assert job_workers(paths) == 8


def test_a_missing_policy_keeps_two_workers(paths) -> None:
    assert job_workers(paths) == 2
