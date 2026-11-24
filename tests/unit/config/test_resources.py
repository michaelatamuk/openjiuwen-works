from __future__ import annotations

from pathlib import Path

from works.config import resources
from works.config.paths import WorksPaths


def test_default_flows_ship_and_copy_into_a_fresh_home(tmp_path: Path) -> None:
    target = tmp_path / "flows"
    assert resources.copy_default_flows(target) is True
    assert (target / "fix-issue.yaml").is_file()
    assert (target / "fix-issue" / "prompts" / "build.md").is_file()
    assert resources.copy_default_flows(target) is False


def test_paths_populate_flows_on_ensure(tmp_path: Path) -> None:
    paths = WorksPaths(tmp_path / "home").ensure()
    assert (paths.flows / "fix-issue.yaml").is_file()
    assert (paths.flows / "fix-issue" / "prompts" / "build.md").is_file()


def test_worker_and_prompt_paths_resolve_from_the_source_tree() -> None:
    worker = resources.worker("agent_chat_worker.py")
    assert worker is not None and worker.is_file()
    prompt = resources.flow_file("fix-issue/prompts/build.md")
    assert prompt is not None and prompt.is_file()
    assert resources.worker("absent-worker.py") is None
