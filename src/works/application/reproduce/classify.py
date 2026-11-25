"""A failure is not always the bug: a missing dependency is a setup problem."""

from __future__ import annotations

DEPS_MARKERS = (
    "ModuleNotFoundError",
    "No module named",
    "Cannot find module",
    "command not found",
    "is not recognized as an internal or external command",
    "no such file or directory",
)


def is_setup_failure(output: str) -> bool:
    return any(marker.lower() in output.lower() for marker in DEPS_MARKERS)
