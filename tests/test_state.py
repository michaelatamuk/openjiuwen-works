from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from works.domain.errors import StateError
from works.domain.records import TaskState
from works.domain.state import ALLOWED, TERMINAL, can_transition, require_transition

S = TaskState
ALL_STATES = list(TaskState)


@pytest.mark.parametrize("source", ALL_STATES)
def test_edges_match_the_table(source: TaskState) -> None:
    for target in ALL_STATES:
        if can_transition(source, target):
            require_transition(source, target)
        else:
            with pytest.raises(StateError):
                require_transition(source, target)


def test_terminal_states_are_terminal() -> None:
    for state in TERMINAL:
        assert ALLOWED[state] == frozenset()


def test_every_state_is_reachable_from_queued() -> None:
    seen = {S.QUEUED}
    frontier = [S.QUEUED]
    while frontier:
        current = frontier.pop()
        for target in ALLOWED[current]:
            if target not in seen:
                seen.add(target)
                frontier.append(target)
    assert seen == set(TaskState)


@given(st.lists(st.sampled_from(ALL_STATES), min_size=1, max_size=30))
@settings(max_examples=200, deadline=None)
def test_random_sequences_follow_the_table(targets: list[TaskState]) -> None:
    current = S.QUEUED
    for target in targets:
        if can_transition(current, target):
            require_transition(current, target)
            current = target
        else:
            with pytest.raises(StateError):
                require_transition(current, target)


def test_a_blocked_task_can_never_be_reopened() -> None:
    for target in ALL_STATES:
        assert not can_transition(S.BLOCKED, target)
