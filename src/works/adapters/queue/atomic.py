"""Atomic file writes for the append-only stores."""

from __future__ import annotations

import os
import time
from pathlib import Path


def atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    for attempt in range(10):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            # Windows scanners and indexers briefly hold freshly written files.
            if attempt == 9:
                raise
            time.sleep(0.02 * (attempt + 1))
