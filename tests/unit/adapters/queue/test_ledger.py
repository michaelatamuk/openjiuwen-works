from __future__ import annotations

from pathlib import Path

import pytest

from works.adapters.queue.ledger import Ledger
from works.domain.errors import StateError
from works.domain.records import LedgerRow, TaskState


def test_append_and_read(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    assert ledger.rows() == []
    ledger.append(LedgerRow(task_id="t-1", run_id="r-1", state=TaskState.PROVED, verdict="allow"))
    ledger.append(LedgerRow(task_id="t-2", run_id="r-2", state=TaskState.BLOCKED))
    rows = ledger.rows()
    assert [row.task_id for row in rows] == ["t-1", "t-2"]
    assert ledger.has_run("r-1")
    assert not ledger.has_run("r-9")


def test_rows_carry_a_schema_version(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.append(LedgerRow(task_id="t-1", state=TaskState.PROVED))
    text = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")
    assert '"schema_version":1' in text
    assert text.endswith("\n")


def test_a_broken_line_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text('{"task_id": "t-1"}\n', encoding="utf-8", newline="\n")
    with pytest.raises(StateError):
        Ledger(path).rows()
