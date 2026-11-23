from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from works.adapters.harness.base import ProposalRequest
from works.adapters.harness.openjiuwen.builder import builder_prompt
from works.application.prompts import load_prompt
from works.domain.errors import ConfigError


def request(title: str = "add subtracts") -> ProposalRequest:
    return ProposalRequest(
        task_id="t-1",
        source_ref="GH-1",
        title=title,
        worktree=Path("C:/work/repo"),
        base_commit="abc1234",
    )


def test_the_shipped_prompt_has_a_stable_hash_and_renders() -> None:
    prompt = load_prompt(Path("flows/fix-issue/prompts/build.md"))
    assert prompt.sha256 == hashlib.sha256(prompt.text.encode("utf-8")).hexdigest()
    rendered = builder_prompt(request(), prompt)
    assert "work" in rendered and "repo" in rendered
    assert "GH-1" in rendered
    assert "<<<" in rendered and ">>>" in rendered
    assert "Do not modify tests" in rendered


def test_a_title_containing_a_dollar_is_not_reinterpreted() -> None:
    rendered = builder_prompt(
        request("costs $100 and $ref is data"),
        load_prompt(Path("flows/fix-issue/prompts/build.md")),
    )
    assert "costs $100 and $ref is data" in rendered


def test_a_prompt_missing_a_variable_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "prompt.md"
    path.write_text("Fix $title in $worktree\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="ref"):
        load_prompt(path)


def test_a_missing_prompt_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_prompt(tmp_path / "absent.md")
