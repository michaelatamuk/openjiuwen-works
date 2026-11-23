"""Task, event and run enums shared by the domain and application layers."""

from __future__ import annotations

from enum import StrEnum


class SourceKind(StrEnum):
    MANUAL = "manual"
    TRACKER = "tracker"
    DETECTOR = "detector"


class TaskKind(StrEnum):
    FIX = "fix"
    CHECK_CHANGE = "check-change"


class TaskState(StrEnum):
    QUEUED = "queued"
    REPRODUCING = "reproducing"
    REPRODUCED = "reproduced"
    PLANNING = "planning"
    PLAN_APPROVED = "plan_approved"
    BUILDING = "building"
    CHECKING = "checking"
    PROVED = "proved"
    WAITING_REVIEW = "waiting_review"
    WAITING_CI = "waiting_ci"
    WAITING_DEPLOY = "waiting_deploy"
    RELEASING = "releasing"
    RELEASED = "released"
    REVERTED = "reverted"
    BLOCKED = "blocked"


class StopReason(StrEnum):
    COMPLETED = "completed"
    NOT_REPRODUCIBLE = "not_reproducible"
    NEEDS_PLAN_APPROVAL = "needs_plan_approval"
    HARNESS_FAILED = "harness_failed"
    POLICY_VIOLATION = "policy_violation"
    TESTS_FAILED = "tests_failed"
    CHALLENGE_FAILED = "challenge_failed"
    VERDICT_FAILED = "verdict_failed"
    BUDGET_EXCEEDED = "budget_exceeded"
    FLAKY_TEST = "flaky_test"
    CONFLICT = "conflict"
    CONFIG_ERROR = "config_error"
    INTERNAL_ERROR = "internal_error"


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
