"""Files shipped with the package: default flows and worker scripts.

Source checkouts keep `flows/` and `scripts/` at the repository root; the wheel maps them under
`works/resources`. Both layouts are resolved here so the CLI works before and after install.
"""

from __future__ import annotations

import shutil
import tempfile
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

RESOURCE_PACKAGE = "works.resources"


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _lookup(*parts: str) -> Traversable | None:
    try:
        base = resources.files(RESOURCE_PACKAGE)
    except (ModuleNotFoundError, TypeError, OSError):
        base = None
    if base is not None:
        candidate = base.joinpath(*parts)
        if candidate.is_file() or candidate.is_dir():
            return candidate
    fallback = repository_root().joinpath(*parts)
    return fallback if fallback.exists() else None


def _materialize(item: Traversable, name: str) -> Path:
    if isinstance(item, Path):
        return item
    target = Path(tempfile.gettempdir()) / "works-resources" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(item.read_bytes())
    return target


def worker(name: str) -> Path | None:
    """A real path to a packaged worker script, or None when it was not shipped."""
    item = _lookup("scripts", name)
    return _materialize(item, name) if item is not None and item.is_file() else None


def flow_file(relative: str) -> Path | None:
    item = _lookup("flows", *relative.split("/"))
    return _materialize(item, relative.replace("/", "-")) if item is not None else None


def copy_default_flows(target: Path) -> bool:
    """Populate a fresh home's `flows/` from the wheel or the source checkout."""
    if target.exists():
        return False
    source = _lookup("flows")
    if source is None or not source.is_dir():
        return False
    _copy(source, target)
    return True


def _copy(source: Traversable, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        destination = target / entry.name
        if entry.is_dir():
            _copy(entry, destination)
        elif entry.is_file():
            destination.write_bytes(entry.read_bytes())


def remove_default_flows(target: Path) -> None:
    """Used by tests and by `works doctor --repair` style cleanup."""
    if target.exists():
        shutil.rmtree(target)
