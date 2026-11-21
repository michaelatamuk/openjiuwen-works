"""Typed errors. One hierarchy, no bare exceptions leaking through the CLI."""

from __future__ import annotations

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_POLICY = 3
EXIT_STATE = 4
EXIT_NOT_FOUND = 5
EXIT_CONFIG = 6
EXIT_CONFLICT = 7
EXIT_BLOCKED = 8


class WorksError(Exception):
    """Base class for every error the product raises on purpose."""

    code = "works_error"
    exit_code = EXIT_INTERNAL


class ConfigError(WorksError):
    """A flow, config file or environment value is missing or malformed."""

    code = "config_error"
    exit_code = EXIT_CONFIG


class PolicyError(WorksError):
    """A change touches a path the policy forbids."""

    code = "policy_error"
    exit_code = EXIT_POLICY


class StateError(WorksError):
    """A transition or approval is not allowed from the current state."""

    code = "state_error"
    exit_code = EXIT_STATE


class NotFoundError(WorksError):
    """A task, run or file does not exist."""

    code = "not_found"
    exit_code = EXIT_NOT_FOUND


class ConflictError(WorksError):
    """A concurrent write lost the race, or an idempotency key is already taken."""

    code = "conflict"
    exit_code = EXIT_CONFLICT


class HarnessError(WorksError):
    """The harness failed, timed out or returned something unusable."""

    code = "harness_error"
    exit_code = EXIT_BLOCKED


class NotImplementedYet(WorksError):
    """A command exists but its milestone has not landed."""

    code = "not_implemented"
    exit_code = EXIT_USAGE


def exit_code_for(exc: BaseException) -> int:
    if isinstance(exc, WorksError):
        return exc.exit_code
    return EXIT_INTERNAL
