"""The ledger: one append-only line per finished run. Never edited, only appended."""

from __future__ import annotations

import os
from pathlib import Path

from filelock import FileLock
from pydantic import ValidationError

from .errors import StateError
from .records import LedgerRow


class Ledger:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock_path = path.with_name(f".{path.name}.lock")

    @property
    def path(self) -> Path:
        return self._path

    def append(self, row: LedgerRow) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with (
            FileLock(str(self._lock_path), timeout=30),
            self._path.open("a", encoding="utf-8", newline="\n") as handle,
        ):
            handle.write(row.model_dump_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def rows(self) -> list[LedgerRow]:
        if not self._path.exists():
            return []
        rows: list[LedgerRow] = []
        for number, line in enumerate(self._path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(LedgerRow.model_validate_json(line))
            except ValidationError as exc:
                raise StateError(f"{self._path}:{number} is not a valid ledger row: {exc}") from exc
        return rows

    def has_run(self, run_id: str) -> bool:
        return any(row.run_id == run_id for row in self.rows())
