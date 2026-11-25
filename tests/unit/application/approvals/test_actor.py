from __future__ import annotations

import pytest

from works.application.approvals.gates import check_actor
from works.domain.errors import ConfigError


def test_a_scheduler_cannot_decide_a_gate() -> None:
    with pytest.raises(ConfigError, match="person must approve"):
        check_actor("scheduler", "scheduler")


def test_an_agent_kind_cannot_decide_a_gate() -> None:
    with pytest.raises(ConfigError, match="person must approve"):
        check_actor("builder", "person")


def test_a_named_person_can_decide() -> None:
    assert check_actor("anna", "person") == "anna"
