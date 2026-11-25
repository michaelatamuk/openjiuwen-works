"""The adapter version a proof records, so a model swap is visible in the evidence."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def package_version(name: str) -> str:
    try:
        return version(name)
    except (PackageNotFoundError, ValueError):
        return "unknown"
