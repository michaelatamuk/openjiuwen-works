from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from works.flakes import FlakeStatus, active_flakes, add_flake, load_flakes
from works.gitops import init_repo
from works.trusted import load_trusted_flow


def test_flow_and_checks_come_from_the_base_commit(tmp_path: Path, paths) -> None:
    destination = tmp_path / "trusted"
    shutil.copytree(paths.flows.parent / "flows", destination / "flows")
    repo = init_repo(destination)
    base = repo.head()

    trusted = load_trusted_flow(repo, base, "fix-issue", paths.flows)
    assert trusted.source == f"git:{base}:flows/fix-issue.yaml"
    assert trusted.flow.node("reproduce").cmd == "{python} -m pytest -q"

    worktree = destination / "flows" / "fix-issue.yaml"
    worktree.write_text(
        worktree.read_text(encoding="utf-8").replace("pytest -q", "pytest -x"),
        encoding="utf-8",
        newline="\n",
    )
    again = load_trusted_flow(repo, base, "fix-issue", paths.flows)
    assert again.flow.node("reproduce").cmd == "{python} -m pytest -q"
    assert again.checks_sha == trusted.checks_sha


def test_a_check_change_changes_the_digest(tmp_path: Path, paths) -> None:
    destination = tmp_path / "trusted"
    shutil.copytree(paths.flows.parent / "flows", destination / "flows")
    policy = destination / "src" / "works" / "policy.py"
    policy.parent.mkdir(parents=True)
    policy.write_text("# policy v1\n", encoding="utf-8")
    repo = init_repo(destination)
    first = load_trusted_flow(repo, repo.head(), "fix-issue", paths.flows)

    policy.write_text("# policy v2\n", encoding="utf-8")
    repo._git("add", "-A")
    repo._git("-c", "user.name=works", "-c", "user.email=works@local", "commit", "-qm", "policy")
    second = load_trusted_flow(repo, repo.head(), "fix-issue", paths.flows)
    assert second.checks_sha != first.checks_sha


def test_flakes_have_an_owner_and_expire(paths) -> None:
    now = datetime(2026, 11, 21, tzinfo=UTC)
    flake = add_flake(
        paths,
        task_id="t-1",
        scenario_id="add-negative",
        owner="michael",
        reason="times out on Windows",
        days=14,
        now=now,
    )
    assert flake.status is FlakeStatus.OPEN
    assert [item.id for item in load_flakes(paths)] == [flake.id]
    assert [item.id for item in active_flakes(paths, now=now)] == [flake.id]
    assert active_flakes(paths, now=now + timedelta(days=15)) == []
