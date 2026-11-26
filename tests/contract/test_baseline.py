from __future__ import annotations

import json
import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXPECTED = {
    "health.json",
    "products.json",
    "detectors.json",
    "tasks.json",
    "metrics.json",
    "ledger.json",
    "task-seed-queued-1.json",
    "task-seed-planning-1.json",
    "task-seed-proved-1.json",
    "task-seed-released-1.json",
    "task-seed-blocked-1.json",
    "runs-seed-queued-1.json",
    "runs-seed-planning-1.json",
    "runs-seed-proved-1.json",
    "runs-seed-released-1.json",
    "runs-seed-blocked-1.json",
}
DETAIL_SECTIONS = {
    "task",
    "summary",
    "run",
    "evidence",
    "proof_md",
    "proof_summary",
    "timeline",
    "pipeline",
    "readiness",
    "features",
    "release",
    "delivery",
    "deployment",
    "confirmation",
    "team",
    "laix",
    "verifier",
    "artifacts",
    "runs",
    "thread",
    "rail",
}


def fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_every_fixture_is_recorded() -> None:
    present = {path.name for path in FIXTURES.glob("*.json")}
    assert present == EXPECTED


def test_task_list_has_all_seed_states() -> None:
    payload = fixture("tasks.json")
    assert isinstance(payload, dict)
    states = {task["state"] for task in payload["tasks"]}
    assert states == {"queued", "planning", "proved", "released", "blocked"}
    assert len(payload["tasks"]) == 5


def test_every_task_detail_has_the_ui_sections() -> None:
    for name in sorted(EXPECTED):
        if not name.startswith("task-"):
            continue
        detail = fixture(name)
        assert isinstance(detail, dict)
        assert set(detail) >= DETAIL_SECTIONS, name
        assert detail["summary"]["id"] == "<task-id>"


def test_text_is_canonicalized() -> None:
    joined = "\n".join(path.read_text(encoding="utf-8") for path in sorted(FIXTURES.glob("*.json")))
    assert not re.search(r"[A-Za-z]:\\\\", joined), "absolute Windows paths leaked into fixtures"
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", joined), "timestamps leaked"
    assert "<task-id>" in joined
    assert "<run-id>" in joined


def test_health_is_a_stable_subset() -> None:
    health = fixture("health.json")
    assert health == {
        "ok": True,
        "readonly": True,
        "write": False,
        "root": "<home>",
        "version": "0.0.1",
        "has_ai": True,
        "has_builder": True,
    }


def test_released_detail_carries_delivery_confirmation_and_deployment() -> None:
    detail = fixture("task-seed-released-1.json")
    assert isinstance(detail, dict)
    assert detail["delivery"]["branch"] == "works/seed-delivered"
    assert detail["confirmation"]["ok"] is True
    assert detail["deployment"]["status"] == "deployed"


def test_blocked_detail_explains_the_stop() -> None:
    detail = fixture("task-seed-blocked-1.json")
    assert isinstance(detail, dict)
    assert detail["pipeline"]["blocked"] is not None
