from __future__ import annotations

import importlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.unit.domain.test_evidence import fixed_evidence
from works.adapters.git.repo import GitRepo
from works.adapters.processes.runner import SubprocessRunner
from works.adapters.queue.store import Queue
from works.application.delivery.deliver import (
    Delivery,
    GitHubForge,
    branch_name,
    deliver,
    repository_slug,
)
from works.application.delivery.release import approve_release
from works.domain.errors import ConfigError
from works.domain.evidence import write_evidence
from works.domain.records import RunRecord, Source, SourceKind, StopReason, TaskState


def _released(paths, repo: GitRepo, *, run_id: str = "r-deliver", ref: str = "GH-DELIVER"):
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref=ref, title="add subtracts"),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(repo.path),
    )
    for state in (
        TaskState.REPRODUCING,
        TaskState.REPRODUCED,
        TaskState.PLANNING,
        TaskState.PLAN_APPROVED,
        TaskState.BUILDING,
        TaskState.CHECKING,
        TaskState.PROVED,
    ):
        queue.transition(task.id, state)
    base = repo.head()
    queue.append(task.id, "gate.decided", {"gate": "plan", "by": "cli", "commit": base})
    worktree = paths.worktrees / run_id / "repo"
    repo.worktree_add(worktree, base)
    core = worktree / "calc" / "core.py"
    core.write_text(
        core.read_text(encoding="utf-8").replace("return a - b", "return a + b"),
        encoding="utf-8",
        newline="\n",
    )
    git = GitRepo(worktree)
    evidence = fixed_evidence().model_copy(
        update={
            "task_id": task.id,
            "run_id": run_id,
            "base_commit": base,
            "state": TaskState.PROVED,
            "files_changed": ["calc/core.py"],
            "diff": git.diff_text(worktree),
        }
    )
    run_dir = paths.runs / run_id
    run_dir.mkdir(parents=True)
    write_evidence(run_dir, evidence)
    now = datetime.now(tz=UTC)
    record = RunRecord(
        run_id=run_id,
        task_id=task.id,
        flow="fix-issue",
        state=TaskState.PROVED,
        stop_reason=StopReason.COMPLETED,
        base_commit=base,
        started_at=now,
        finished_at=now,
    )
    (run_dir / "run.json").write_text(record.model_dump_json(indent=2), encoding="utf-8")
    released, _, _ = approve_release(paths, task.id)
    return released, worktree, base


def _remote(tmp_path: Path, repo: GitRepo) -> Path:
    remote = tmp_path / "remote.git"
    runner = SubprocessRunner()
    assert runner.run(["git", "init", "--bare", "-q", str(remote)], tmp_path).ok
    assert runner.run(
        ["git", "-C", str(repo.path), "remote", "add", "origin", str(remote)], repo.path
    ).ok
    return remote


def test_delivery_commits_the_approved_diff_and_pushes_a_branch(paths, repo, tmp_path) -> None:
    task, worktree, base = _released(paths, repo)
    _remote(tmp_path, repo)

    delivery = deliver(paths, task.id, provider="none")

    assert delivery.pushed is True
    assert delivery.branch == branch_name(task.id)
    assert delivery.commit != base
    assert repo.remote_commit("origin", delivery.branch) == delivery.commit
    assert (paths.runs / "r-deliver" / "delivery.json").exists()
    # The builder's worktree now holds the delivered commit.
    assert GitRepo(worktree).head() == delivery.commit
    assert "Works-Run: r-deliver" in GitRepo(worktree)._git("log", "-1", "--format=%B").stdout


def test_delivery_is_idempotent(paths, repo, tmp_path) -> None:
    task, _, _ = _released(paths, repo)
    _remote(tmp_path, repo)

    first = deliver(paths, task.id)
    second = deliver(paths, task.id)

    assert first.created is True
    assert second.created is False
    assert second.commit == first.commit
    events = [e for e in Queue(paths).events(task.id) if e.type == "delivery.finished"]
    assert len(events) == 1


def test_a_dry_run_commits_but_does_not_push(paths, repo) -> None:
    task, _, _ = _released(paths, repo)
    _remote_forbidden = repo.has_remote("origin")
    assert _remote_forbidden is False

    delivery = deliver(paths, task.id, dry_run=True)

    assert delivery.dry_run is True
    assert delivery.pushed is False
    assert delivery.commit


def test_delivery_requires_gate_two(paths, repo) -> None:
    _released(paths, repo)
    queue = Queue(paths)
    # Move a copy of the task back to proved by starting a second, unreleased task.
    second, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="GH-SECOND", title="not released"),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(repo.path),
    )

    with pytest.raises(ConfigError, match="gate 2"):
        deliver(paths, second.id)


def test_a_clean_worktree_has_nothing_to_deliver(paths, repo, tmp_path) -> None:
    task, worktree, base = _released(paths, repo)
    _remote(tmp_path, repo)
    clean = GitRepo(worktree)
    clean.stage_all()
    clean.commit_staged("already committed")
    clean._git("reset", "--hard", base)

    with pytest.raises(ConfigError, match="no change to deliver"):
        deliver(paths, task.id)


def test_the_repository_slug_handles_https_and_ssh() -> None:
    assert repository_slug("https://github.com/owner/name.git") == "owner/name"
    assert repository_slug("git@github.com:owner/name.git") == "owner/name"
    assert repository_slug("C:/local/bare.git") is None


class FakeGitHub:
    def __init__(self, *, comments: list[dict] | None = None, pulls: list[dict] | None = None):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.pulls = pulls or []
        self.comments = comments or []

    def __call__(self, url, method, headers, payload):
        self.calls.append((url, method, payload))
        if method == "GET" and "/pulls" in url:
            return 200, self.pulls
        if method == "POST" and url.endswith("/pulls"):
            return 201, {"html_url": "https://github.com/o/r/pull/7"}
        if method == "GET" and "/comments" in url:
            return 200, self.comments
        if method == "POST" and url.endswith("/comments"):
            return 201, {"html_url": "https://github.com/o/r/issues/3#c1"}
        if method == "PATCH":
            return 200, {"state": "closed"}
        return 404, {"message": "unexpected"}


def test_the_forge_reuses_an_existing_pull_request() -> None:
    transport = FakeGitHub(pulls=[{"html_url": "https://github.com/o/r/pull/1"}])
    forge = GitHubForge(token="secret", transport=transport)  # noqa: S106

    url = forge.ensure_pull_request(
        repository="o/r", head="works/t-1", base="main", title="t", body="b"
    )

    assert url == "https://github.com/o/r/pull/1"
    assert len(transport.calls) == 1


def test_the_forge_creates_a_pull_request() -> None:
    transport = FakeGitHub()
    forge = GitHubForge(token="secret", transport=transport)  # noqa: S106

    pr = forge.ensure_pull_request(
        repository="o/r", head="works/t-1", base="main", title="t", body="b"
    )

    assert pr.endswith("/pull/7")
    assert [call[1] for call in transport.calls] == ["GET", "POST"]


def test_the_forge_needs_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(ConfigError, match="GITHUB_TOKEN"):
        GitHubForge(transport=FakeGitHub()).ensure_pull_request(
            repository="o/r", head="h", base="main", title="t", body="b"
        )


def test_delivery_can_reuse_a_previous_dry_run(paths, repo, tmp_path) -> None:
    task, _, _ = _released(paths, repo)
    _remote(tmp_path, repo)
    dry = deliver(paths, task.id, dry_run=True)

    real = deliver(paths, task.id)

    assert real.created is True
    assert real.commit == dry.commit
    assert real.pushed is True


def test_delivery_reuses_the_record_when_the_worktree_is_gone(paths, repo, tmp_path) -> None:
    task, worktree, _ = _released(paths, repo)
    _remote(tmp_path, repo)
    first = deliver(paths, task.id)
    repo.worktree_remove(worktree)

    second = deliver(paths, task.id)

    assert second.created is False
    assert second.commit == first.commit


class FakeTracker:
    def __init__(self) -> None:
        self.comments: list[tuple[str, str, str]] = []

    def ensure_comment(self, *, ref, body, marker):
        self.comments.append((ref, body, marker))
        return "https://jira.example/FIRE-3#comment"

    def close(self, *, ref) -> None:
        pass


def test_delivery_returns_to_a_jira_tracker(paths, repo, tmp_path) -> None:
    task, _, _ = _released(paths, repo, ref="FIRE-3")
    _remote(tmp_path, repo)
    tracker = FakeTracker()

    delivery = deliver(paths, task.id, tracker="jira", tracker_client=tracker)

    assert delivery.comment_url == "https://jira.example/FIRE-3#comment"
    assert tracker.comments[0][0] == "FIRE-3"
    assert "<!-- works-run: r-deliver -->" in tracker.comments[0][1]


def test_an_explicit_tracker_that_cannot_read_the_ref_is_refused(paths, repo, tmp_path) -> None:
    task, _, _ = _released(paths, repo, ref="GH-DELIVER")
    _remote(tmp_path, repo)

    with pytest.raises(ConfigError, match="cannot return"):
        deliver(paths, task.id, provider="none", tracker="jira")


def test_delivery_exposes_a_stable_record(paths, repo, tmp_path) -> None:
    task, _, _ = _released(paths, repo)
    _remote(tmp_path, repo)
    delivery = deliver(paths, task.id)

    assert Delivery(**delivery.as_dict()).commit == delivery.commit


class _IdempotentForge:
    """A forge that finds its own pull request by head, like the real one does by marker."""

    def __init__(self) -> None:
        self.pulls: dict[str, str] = {}
        self.created = 0

    def ensure_pull_request(self, *, repository, head, base, title, body):
        if head not in self.pulls:
            self.created += 1
            self.pulls[head] = f"https://github.com/{repository}/pull/{self.created}"
        return self.pulls[head]


class _CrashingTracker:
    def __init__(self) -> None:
        self.calls = 0

    def ensure_comment(self, *, ref, body, marker):
        self.calls += 1
        raise RuntimeError("the daemon died before the comment was recorded")

    def close(self, *, ref) -> None:
        pass


def test_a_crash_after_the_pull_request_does_not_create_a_second(
    paths, repo, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, _, _ = _released(paths, repo, ref="FIRE-3")
    _remote(tmp_path, repo)
    monkeypatch.setattr("works.application.delivery.deliver.repository_slug", lambda url: "o/r")
    forge = _IdempotentForge()

    with pytest.raises(RuntimeError, match="died before the comment"):
        deliver(
            paths,
            task.id,
            provider="github",
            forge=forge,
            tracker="jira",
            tracker_client=_CrashingTracker(),
        )
    assert not (paths.runs / "r-deliver" / "delivery.json").exists()

    tracker = FakeTracker()
    second = deliver(
        paths,
        task.id,
        provider="github",
        forge=forge,
        tracker="jira",
        tracker_client=tracker,
    )

    assert forge.created == 1
    assert list(forge.pulls.values()) == [second.pr_url]
    assert len(tracker.comments) == 1
    events = [e for e in Queue(paths).events(task.id) if e.type == "delivery.finished"]
    assert len(events) == 1


def test_a_crash_before_the_record_is_written_is_recovered(
    paths, repo, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, _, _ = _released(paths, repo)
    _remote(tmp_path, repo)
    real_write = importlib.import_module("works.application.delivery.deliver")._write_delivery
    calls = {"n": 0}

    def flaky(run_dir, delivery):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("the daemon died before the record was written")
        real_write(run_dir, delivery)

    monkeypatch.setattr("works.application.delivery.deliver._write_delivery", flaky)

    with pytest.raises(RuntimeError, match="died before the record"):
        deliver(paths, task.id)
    assert not (paths.runs / "r-deliver" / "delivery.json").exists()

    second = deliver(paths, task.id)

    assert second.created is True
    assert (paths.runs / "r-deliver" / "delivery.json").exists()
    events = [e for e in Queue(paths).events(task.id) if e.type == "delivery.finished"]
    assert len(events) == 1
