from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import check_prompts


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    flows = tmp_path / "flows" / "fix-issue" / "prompts"
    flows.mkdir(parents=True)
    (flows / "build.md").write_text("Work on $title for $ref.\n", encoding="utf-8")
    monkeypatch.setattr(check_prompts, "ROOT", tmp_path)
    monkeypatch.setattr(check_prompts, "REGISTRY", tmp_path / "flows" / "prompts.lock.json")
    return flows


def test_the_shipped_registry_matches_every_prompt() -> None:
    assert check_prompts.problems() == []


def test_an_edited_prompt_is_a_mismatch(tmp_path, monkeypatch) -> None:
    flows = _workspace(tmp_path, monkeypatch)
    check_prompts.update()

    (flows / "build.md").write_text("Work on $title.\n", encoding="utf-8")

    assert any("hash mismatch" in item for item in check_prompts.problems())


def test_an_unregistered_prompt_is_reported(tmp_path, monkeypatch) -> None:
    flows = _workspace(tmp_path, monkeypatch)
    check_prompts.update()
    (flows / "extra.md").write_text("Extra $title $ref $worktree\n", encoding="utf-8")

    assert any("not registered" in item for item in check_prompts.problems())


def test_update_preserves_owner_and_changelog(tmp_path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    check_prompts.update()
    payload = json.loads(check_prompts.REGISTRY.read_text(encoding="utf-8"))
    payload["prompts"][0]["owner"] = "mira-team"
    payload["prompts"][0]["changelog"].append(
        {"version": 2, "date": "2026-11-26", "note": "added a refusal clause"}
    )
    check_prompts.REGISTRY.write_text(json.dumps(payload), encoding="utf-8")

    check_prompts.update()

    saved = json.loads(check_prompts.REGISTRY.read_text(encoding="utf-8"))["prompts"][0]
    assert saved["owner"] == "mira-team"
    assert len(saved["changelog"]) == 2


def test_a_crlf_checkout_hashes_like_an_lf_checkout(tmp_path, monkeypatch) -> None:
    flows = _workspace(tmp_path, monkeypatch)
    (flows / "build.md").write_bytes(b"Work on $title for $ref.\r\n")
    check_prompts.update()

    (flows / "build.md").write_bytes(b"Work on $title for $ref.\n")

    assert check_prompts.problems() == []
