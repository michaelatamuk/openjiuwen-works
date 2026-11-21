"""A derived SQLite index for `status`. The JSONL events remain the source of truth.

ADR-002 allows SQLite behind an interface once the queue passes a few hundred tasks. The load
target in the engineering standard (10 000 tasks, `status` under 100 ms) is exactly that point.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    flow TEXT NOT NULL,
    product TEXT NOT NULL,
    repo TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    source_title TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

SUMMARY_COLUMNS = (
    "id",
    "state",
    "flow",
    "source_kind",
    "source_ref",
    "attempts",
    "created_at",
)


def summary_row(payload: dict[str, Any]) -> tuple[Any, ...]:
    source = payload.get("source") or {}
    return (
        payload["id"],
        payload["state"],
        payload["flow"],
        payload.get("product", ""),
        payload.get("repo", ""),
        source.get("kind", ""),
        source.get("ref", ""),
        source.get("title", ""),
        int(payload.get("attempts", 0)),
        payload.get("created_at", ""),
        payload.get("updated_at", ""),
    )


def summary_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "state": row["state"],
        "flow": row["flow"],
        "source": {
            "kind": row["source_kind"],
            "ref": row["source_ref"],
        },
        "attempts": row["attempts"],
        "created_at": row["created_at"],
    }


class TaskIndex:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def upsert(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(SCHEMA)
            connection.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "state=excluded.state, flow=excluded.flow, product=excluded.product, "
                "repo=excluded.repo, source_kind=excluded.source_kind, "
                "source_ref=excluded.source_ref, source_title=excluded.source_title, "
                "attempts=excluded.attempts, created_at=excluded.created_at, "
                "updated_at=excluded.updated_at",
                summary_row(payload),
            )

    def replace(self, payloads: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._replace_once(payloads)
        except sqlite3.DatabaseError:
            for suffix in ("", "-wal", "-shm"):
                Path(f"{self._path}{suffix}").unlink(missing_ok=True)
            self._replace_once(payloads)

    def _replace_once(self, payloads: list[dict[str, Any]]) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(SCHEMA)
            connection.execute("DELETE FROM tasks")
            connection.executemany(
                "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [summary_row(payload) for payload in payloads],
            )

    def list(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT {', '.join(SUMMARY_COLUMNS)} FROM tasks ORDER BY created_at, id"  # noqa: S608  # nosec B608
            ).fetchall()
        return [summary_dict(row) for row in rows]

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT {', '.join(SUMMARY_COLUMNS)} FROM tasks WHERE id = ?",  # noqa: S608  # nosec B608
                (task_id,),
            ).fetchone()
        return summary_dict(row) if row is not None else None

    def count(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()
        return int(row["n"])
