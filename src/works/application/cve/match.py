"""Does a pinned version fall inside an advisory's range?"""

from __future__ import annotations

import re

from packaging.version import InvalidVersion, Version

from works.application.cve.feed import Advisory

_SEMVER = re.compile(r"^[vV]?(\d+(?:\.\d+)*)(?:[-+].*)?$")


def _semver(text: str) -> tuple[int, ...] | None:
    match = _SEMVER.match(text.strip())
    if match is None:
        return None
    parts = [int(item) for item in match.group(1).split(".")]
    return tuple(parts + [0] * (3 - len(parts)))[:3]


def compare(left: str, right: str, ecosystem: str) -> int:
    """-1, 0 or 1; falls back to text when a version is not comparable."""
    if ecosystem.lower() in {"pypi", "python"}:
        try:
            parsed_left, parsed_right = Version(left), Version(right)
        except InvalidVersion:
            return (left > right) - (left < right)
        return (parsed_left > parsed_right) - (parsed_left < parsed_right)
    left_semver, right_semver = _semver(left), _semver(right)
    if left_semver is None or right_semver is None:
        return (left > right) - (left < right)
    return (left_semver > right_semver) - (left_semver < right_semver)


def is_affected(version: str, advisory: Advisory, ecosystem: str) -> bool:
    if advisory.versions and version in advisory.versions:
        return True
    for introduced, fixed, last in advisory.ranges:
        if introduced not in (None, "", "0", "*") and compare(version, introduced, ecosystem) < 0:
            continue
        if fixed is not None and compare(version, fixed, ecosystem) >= 0:
            continue
        if last is not None and compare(version, last, ecosystem) > 0:
            continue
        return True
    return False


def fixed_version(advisory: Advisory) -> str | None:
    for _introduced, fixed, _last in advisory.ranges:
        if fixed:
            return fixed
    return None
