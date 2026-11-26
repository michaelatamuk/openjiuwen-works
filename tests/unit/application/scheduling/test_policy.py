from __future__ import annotations

from pathlib import Path

import pytest

from works.application.scheduling.policy import (
    DispatchPolicy,
    in_blackout,
    inside_window,
    load_policy,
    parse_window,
    policy_path,
    risk_for_severity,
    set_enabled,
)
from works.domain.errors import ConfigError


def _write(paths, text: str) -> Path:
    path = policy_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_a_missing_policy_is_disabled(paths) -> None:
    policy = load_policy(paths)

    assert policy.enabled is False
    assert policy.concurrency.global_slots == 2
    assert policy.concurrency.per_repo == 1


def test_a_full_policy_loads_and_validates(paths) -> None:
    _write(
        paths,
        """
enabled: true
tick_seconds: 5
levels:
  default: L1
  by_source:
    detector: L2
allow:
  sources: [github, detector]
  labels: ["works:auto"]
  manual: true
concurrency:
  global: 3
  per_repo: 1
budget:
  daily_usd: 12
  per_run_usd: 4
windows:
  blackout: ["02:00-02:30"]
""",
    )

    policy = load_policy(paths)

    assert policy.enabled is True
    assert policy.tick_seconds == 5
    assert policy.levels.by_source["detector"] == "L2"
    assert policy.allow.manual is True
    assert policy.concurrency.global_slots == 3
    assert policy.budget.daily_usd == 12


def test_an_unknown_key_is_a_config_error(paths) -> None:
    _write(paths, "enabled: true\nsurprise: 1\n")

    with pytest.raises(ConfigError, match="not a valid dispatch policy"):
        load_policy(paths)


def test_a_bad_window_is_a_config_error(paths) -> None:
    _write(paths, 'enabled: true\nwindows:\n  blackout: ["25:00-26:00"]\n')

    with pytest.raises(ConfigError, match="not a valid dispatch policy"):
        load_policy(paths)


def test_enable_keeps_comments_and_other_keys(paths) -> None:
    path = _write(paths, "# keep me\nenabled: false\ntick_seconds: 7\n")

    set_enabled(paths, True)

    text = path.read_text(encoding="utf-8")
    assert "# keep me" in text
    assert "enabled: true" in text
    assert "tick_seconds: 7" in text
    assert load_policy(paths).enabled is True


def test_enable_creates_a_minimal_file(paths) -> None:
    set_enabled(paths, True)

    assert load_policy(paths).enabled is True


def test_windows_wrap_midnight() -> None:
    from datetime import UTC, datetime

    start, end = parse_window("22:00-02:00")
    assert start.hour == 22
    assert end.hour == 2
    assert inside_window(datetime(2026, 11, 25, 23, 30, tzinfo=UTC), "22:00-02:00") is True
    assert inside_window(datetime(2026, 11, 25, 12, 0, tzinfo=UTC), "22:00-02:00") is False


def test_severity_maps_to_risk() -> None:
    assert risk_for_severity("S1") == "critical"
    assert risk_for_severity("S4") == "low"
    assert risk_for_severity(None) == "medium"


def test_blackout_is_checked_against_the_policy(paths) -> None:
    from datetime import UTC, datetime

    policy = DispatchPolicy.model_validate({"windows": {"blackout": ["00:00-23:59"]}})

    assert in_blackout(policy, datetime(2026, 11, 25, 10, 0, tzinfo=UTC)) is True


def test_a_non_mapping_policy_is_refused(paths) -> None:
    _write(paths, "- 1\n- 2\n")

    with pytest.raises(ConfigError, match="must be a mapping"):
        load_policy(paths)


def test_a_malformed_window_is_refused() -> None:
    with pytest.raises(ValueError, match="HH:MM-HH:MM"):
        parse_window("10:00")


def test_enable_inserts_the_key_when_missing(paths) -> None:
    path = _write(paths, "tick_seconds: 7\n")

    set_enabled(paths, True)

    assert load_policy(paths).enabled is True
    assert "tick_seconds: 7" in path.read_text(encoding="utf-8")
