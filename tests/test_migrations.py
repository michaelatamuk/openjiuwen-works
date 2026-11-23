from __future__ import annotations

import json
from pathlib import Path

import pytest

from works.adapters.queue.migrations import migrate_task
from works.application.schema import all_schemas
from works.domain.errors import StateError
from works.domain.records import TaskState


def test_a_v0_task_loads_through_the_migration() -> None:
    path = Path(__file__).parent / "fixtures" / "schema-v0-task.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    migrated = migrate_task(raw)
    assert migrated["schema_version"] == 1
    assert migrated["state"] == "building"
    assert migrated["product"] == "unknown"
    assert migrated["source"] == {"kind": "manual", "ref": "GH-1", "title": ""}


def test_migration_is_idempotent() -> None:
    raw = {
        "schema_version": 1,
        "id": "t-1",
        "flow": "f",
        "product": "p",
        "repo": ".",
        "source": {"kind": "manual", "ref": "1"},
    }
    once = migrate_task(raw)
    assert migrate_task(once) == once


def test_a_newer_schema_is_refused() -> None:
    with pytest.raises(StateError):
        migrate_task({"schema_version": 99, "id": "t-1"})


def test_a_non_mapping_is_refused() -> None:
    with pytest.raises(StateError):
        migrate_task(["not", "a", "task"])


def test_every_persisted_schema_is_printed() -> None:
    payload = all_schemas()
    assert payload["schema_version"] == 1
    for name in (
        "task",
        "event",
        "run",
        "verdict",
        "ledger",
        "command",
        "evidence",
        "proposal",
        "finding",
        "challenge",
    ):
        assert name in payload["schemas"]
        assert payload["schemas"][name]["type"] == "object"


def test_legacy_states_map_to_real_states() -> None:
    for legacy in ("new", "running", "done", "failed", "needs_person"):
        migrated = migrate_task(
            {
                "schema_version": 0,
                "id": "t-1",
                "flow": "f",
                "product": "p",
                "repo": ".",
                "state": legacy,
                "source": {"kind": "manual", "ref": "1"},
            }
        )
        assert TaskState(migrated["state"])
