"""Collect the files a preview run leaves behind, with a hash for the proof."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .evidence import Artifact

_KINDS = {
    ".png": "screenshot",
    ".jpg": "screenshot",
    ".jpeg": "screenshot",
    ".webp": "screenshot",
    ".mp4": "video",
    ".webm": "video",
    ".log": "log",
    ".txt": "log",
    ".trace": "trace",
    ".json": "trace",
}


def _kind(path: Path) -> str:
    return _KINDS.get(path.suffix.lower(), "file")


def collect_artifacts(source: Path, destination: Path) -> list[Artifact]:
    """Copy a preview's artifact tree into the run directory and describe every file."""
    if not source.exists():
        return []
    destination.mkdir(parents=True, exist_ok=True)
    artifacts: list[Artifact] = []
    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        artifacts.append(
            Artifact(
                kind=_kind(path),
                path=f"artifacts/{relative.as_posix()}",
                sha256=digest,
                description=path.name,
            )
        )
    return artifacts
