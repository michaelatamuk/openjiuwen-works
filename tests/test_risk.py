from __future__ import annotations

from works.adapters.git.repo import DiffStat
from works.domain.flow import find_flow, load_flow
from works.domain.risk import RiskLevel, rate_risk


def flow(paths):
    return load_flow(find_flow(paths.flows, "fix-issue"))


def stat(path: str, added: int = 1, removed: int = 1) -> DiffStat:
    return DiffStat(path=path, added=added, removed=removed)


def test_docs_only_is_low(paths) -> None:
    rating = rate_risk(paths=["docs/plan.md"], diff_stat=[stat("docs/plan.md")], flow=flow(paths))
    assert rating.level is RiskLevel.LOW
    assert "documentation only" in rating.reasons


def test_a_critical_path_is_high_and_needs_an_owner(paths) -> None:
    rating = rate_risk(
        paths=["auth/login.py"],
        diff_stat=[stat("auth/login.py")],
        flow=flow(paths),
    )
    assert rating.level is RiskLevel.HIGH
    assert rating.rounded_up is True
    assert "michael" in rating.owners
    assert any("critical path" in reason for reason in rating.reasons)


def test_a_large_change_is_medium(paths) -> None:
    files = [f"src/module_{index}.py" for index in range(12)]
    rating = rate_risk(
        paths=files,
        diff_stat=[stat(path) for path in files],
        flow=flow(paths),
    )
    assert rating.level is RiskLevel.MEDIUM
    assert rating.files == 12


def test_an_empty_change_is_low(paths) -> None:
    rating = rate_risk(paths=[], diff_stat=[], flow=flow(paths))
    assert rating.level is RiskLevel.LOW
    assert rating.owners == []
