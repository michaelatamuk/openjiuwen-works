"""Deliver an approved change: branch, commit, push and optionally a pull request.

Gate 2 has already opened; delivery never re-decides. It prepares a branch from the approved proof,
checks that the worktree still matches that proof, pushes it, and (with a token) opens one pull
request and one comment on the source issue. Every step is idempotent: a retry finds the branch,
the earlier delivery record and the existing PR instead of creating duplicates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import WorksPaths
from .errors import ConfigError
from .evidence import Evidence
from .forge import (
    Forge,
    GitHubForge,
    build_forge,
    gitlab_project,
    repository_slug,
)
from .gitops import GitRepo
from .queue import Queue
from .records import RunRecord, Task, TaskState
from .release import latest_run_dir, release_packet
from .runner import CommandRunner, SubprocessRunner
from .tracker import Tracker, build_tracker, tracker_accepts

__all__ = ["Delivery", "GitHubForge", "branch_name", "deliver", "repository_slug"]


def branch_name(task_id: str) -> str:
    return f"works/{task_id}"


@dataclass
class Delivery:
    task_id: str
    run_id: str
    commit: str
    branch: str
    provider: str = "none"
    tracker: str = "none"
    pr_url: str | None = None
    comment_url: str | None = None
    pushed: bool = False
    dry_run: bool = False
    created: bool = True
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "commit": self.commit,
            "branch": self.branch,
            "provider": self.provider,
            "tracker": self.tracker,
            "pr_url": self.pr_url,
            "comment_url": self.comment_url,
            "pushed": self.pushed,
            "dry_run": self.dry_run,
            "created": self.created,
            "notes": self.notes,
        }


def _delivery_message(task: Task, run_id: str, proof_sha256: str | None) -> str:
    title = task.source.title.strip() or task.source.ref
    trailer = [
        f"Works-Task: {task.id}",
        f"Works-Run: {run_id}",
        f"Works-Source: {task.source.kind.value}:{task.source.ref}",
    ]
    if proof_sha256:
        trailer.append(f"Works-Proof: {proof_sha256}")
    return f"{title}\n\n{chr(10).join(trailer)}\n"


def _pull_request_body(
    task: Task, run_id: str, commit: str, proof_sha256: str | None, evidence: Evidence
) -> str:
    verdict = "allow" if evidence.verdict is not None and evidence.verdict.allow else "block"
    lines = [
        task.source.title.strip() or task.source.ref,
        "",
        f"- task: `{task.id}`",
        f"- run: `{run_id}`",
        f"- commit: `{commit}`",
        f"- proof: `{proof_sha256 or 'unbound'}`",
        f"- verdict: **{verdict}**",
        f"- source: `{task.source.kind.value}:{task.source.ref}`",
        "",
        "Opening this pull request is a human decision; the proof is attached below.",
        "",
        f"<!-- works-run: {run_id} -->",
    ]
    return "\n".join(lines)


def _source_marker(run_id: str) -> str:
    return f"<!-- works-run: {run_id} -->"


def _load_delivery(run_dir: Path | None) -> Delivery | None:
    if run_dir is None:
        return None
    path = run_dir / "delivery.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Delivery(**raw)
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _write_delivery(run_dir: Path, delivery: Delivery) -> None:
    (run_dir / "delivery.json").write_text(
        json.dumps(delivery.as_dict(), indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def _prepare_commit(
    task: Task,
    record: RunRecord,
    evidence: Evidence,
    paths: WorksPaths,
    *,
    run_dir: Path,
    runner: CommandRunner,
    notes: list[str],
) -> tuple[GitRepo, Path, str]:
    base = record.base_commit
    if base is None:
        raise ConfigError("the run has no base commit")
    repo = GitRepo(Path(task.repo), runner)
    worktree = paths.worktrees / record.run_id / "repo"
    if not worktree.exists():
        worktree = paths.worktrees / f"{record.run_id}-deliver" / "repo"
        if worktree.exists():
            repo.worktree_remove(worktree)
        repo.worktree_add(worktree, base)
        if evidence.diff.strip():
            repo.apply_patch(worktree, evidence.diff, run_dir / "delivery.diff")
        notes.append("rebuilt the worktree from the approved diff")
    git = GitRepo(worktree, runner)
    if not git.is_dirty():
        commit = git.head()
        if commit == base:
            raise ConfigError(
                "there is no change to deliver: the worktree is clean at the base commit"
            )
        notes.append("the builder left a committed change; delivering that commit")
        return git, worktree, commit
    actual = hashlib.sha256(git.diff_text(worktree).encode("utf-8")).hexdigest()
    if evidence.diff_sha256 and actual != evidence.diff_sha256:
        raise ConfigError("the worktree no longer matches the approved proof; run the task again")
    git.stage_all()
    staged = git.staged_files()
    expected = sorted(evidence.files_changed)
    if expected and sorted(staged) != expected:
        raise ConfigError(f"delivery would commit {staged}, but the proof names {expected}")
    message = _delivery_message(task, record.run_id, evidence.proof_sha256 or None)
    commit = git.commit_staged(message)
    notes.append(f"committed {len(staged)} file(s)")
    return git, worktree, commit


def deliver(
    paths: WorksPaths,
    task_id: str,
    *,
    remote: str = "origin",
    provider: str = "none",
    dry_run: bool = False,
    base_branch: str = "main",
    runner: CommandRunner | None = None,
    forge: Forge | None = None,
    tracker: str | None = None,
    tracker_client: Tracker | None = None,
) -> Delivery:
    effective_tracker = tracker or provider
    if provider not in ("none", "github", "gitlab"):
        raise ConfigError(f"unknown forge {provider!r}; expected none, github or gitlab")
    if effective_tracker not in ("none", "github", "gitlab", "jira"):
        raise ConfigError(
            f"unknown tracker {effective_tracker!r}; expected none, github, gitlab or jira"
        )
    queue = Queue(paths)
    task = queue.load(task_id)
    if task.state is not TaskState.RELEASED:
        raise ConfigError(f"task {task_id} is {task.state.value}; gate 2 must open before delivery")
    packet = release_packet(paths, task_id)
    if not packet.ready:
        raise ConfigError("delivery is blocked: " + "; ".join(packet.blockers))
    run_dir = latest_run_dir(paths, task_id)
    if run_dir is None:
        raise ConfigError("the task has no finished run to deliver")
    record = RunRecord.model_validate_json((run_dir / "run.json").read_text(encoding="utf-8"))
    evidence = Evidence.model_validate_json((run_dir / "evidence.json").read_text(encoding="utf-8"))
    existing = _load_delivery(run_dir)
    branch = branch_name(task.id)
    notes: list[str] = []
    command_runner = runner or SubprocessRunner()
    repo = GitRepo(Path(task.repo), command_runner)
    commit: str | None = None
    if (
        existing is not None
        and existing.branch == branch
        and existing.commit
        and repo.branch_commit(branch) == existing.commit
    ):
        commit = existing.commit
        if (
            not existing.dry_run
            and existing.provider == provider
            and existing.tracker == effective_tracker
            and (provider == "none" or existing.pr_url)
        ):
            existing.created = False
            return existing
        notes.append("reusing the delivered commit")
    if commit is None:
        _git, _worktree, commit = _prepare_commit(
            task,
            record,
            evidence,
            paths,
            run_dir=run_dir,
            runner=command_runner,
            notes=notes,
        )
    repo.set_branch(branch, commit)
    delivery = Delivery(
        task_id=task.id,
        run_id=record.run_id,
        commit=commit,
        branch=branch,
        provider=provider,
        tracker=effective_tracker,
        dry_run=dry_run,
        notes=notes,
    )
    if dry_run:
        delivery.notes.append("dry run: no push and no pull request")
        _write_delivery(run_dir, delivery)
        queue.append(task.id, "delivery.finished", delivery.as_dict())
        return delivery
    if not repo.has_remote(remote):
        raise ConfigError(f"the repository has no remote {remote!r}; nothing to push")
    forger: Forge | None = None
    slug: str | None = None
    if provider != "none":
        remote_url = repo.remote_url(remote)
        slug = repository_slug(remote_url) if provider == "github" else gitlab_project(remote_url)
        if slug is None:
            raise ConfigError(f"cannot read a {provider} owner/repo from {remote_url!r}")
        forger = forge or build_forge(provider)
    tracker_obj = tracker_client
    if tracker_obj is None and effective_tracker != "none":
        tracker_obj = build_tracker(effective_tracker)
    if tracker_obj is not None and not tracker_accepts(effective_tracker, task.source.ref):
        if tracker is not None:
            raise ConfigError(f"tracker {effective_tracker!r} cannot return to {task.source.ref!r}")
        delivery.notes.append(
            f"tracker {effective_tracker}: {task.source.ref} is not handled; comment skipped"
        )
        tracker_obj = None
    repo.push(remote, branch)
    delivery.pushed = True
    if forger is not None and slug is not None:
        delivery.pr_url = forger.ensure_pull_request(
            repository=slug,
            head=branch,
            base=base_branch,
            title=task.source.title.strip() or task.source.ref,
            body=_pull_request_body(
                task, record.run_id, commit, evidence.proof_sha256 or None, evidence
            ),
        )
        delivery.notes.append(f"pull request: {delivery.pr_url}")
    if tracker_obj is not None:
        delivery.comment_url = tracker_obj.ensure_comment(
            ref=task.source.ref,
            body=(
                f"Delivered in `{commit}` on `{branch}`"
                + (f": {delivery.pr_url}" if delivery.pr_url else "")
                + f"\n\n{_source_marker(record.run_id)}"
            ),
            marker=_source_marker(record.run_id),
        )
        delivery.notes.append(f"source comment: {delivery.comment_url}")
    _write_delivery(run_dir, delivery)
    queue.append(task.id, "delivery.finished", delivery.as_dict())
    return delivery
