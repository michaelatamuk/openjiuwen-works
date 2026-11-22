"""Confirm a delivered change against the thing that was released.

Delivery says "the branch and pull request exist". Confirmation says "the released commit still
passes". It checks a fresh worktree at the delivered commit, never the builder's dirty one, and
records one result per run.

There is no universal confirmation target. A CLI or HTTP check is explicit; otherwise Works re-runs
the plan's scenario set. A GUI product needs a real runner, and its absence is reported rather than
replaced by a green claim.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import WorksPaths
from .deliver import _source_marker
from .errors import ConfigError
from .gitops import GitRepo
from .queue import Queue
from .records import TaskState
from .release import latest_run_dir, release_packet
from .runner import CommandResult, CommandRunner, SubprocessRunner
from .scenarios import load_scenario_set
from .tracker import Tracker, build_tracker, tracker_accepts


@dataclass
class Confirmation:
    task_id: str
    run_id: str
    commit: str
    ok: bool
    target: str
    exit_code: int = 0
    duration_ms: int = 0
    output_sha256: str = ""
    notes: list[str] = field(default_factory=list)
    comment_url: str | None = None
    created: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "commit": self.commit,
            "ok": self.ok,
            "target": self.target,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "output_sha256": self.output_sha256,
            "notes": self.notes,
            "comment_url": self.comment_url,
            "created": self.created,
        }


def _load(run_dir: Path | None) -> dict[str, Any] | None:
    if run_dir is None:
        return None
    path = run_dir / "confirmation.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _http_check(url: str) -> tuple[bool, int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "openjiuwen-works"})  # noqa: S310  # nosec B310
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310  # nosec B310
            body = response.read()
            return (
                200 <= response.status < 300,
                response.status,
                body.decode("utf-8", errors="replace"),
            )
    except urllib.error.HTTPError as exc:
        return False, exc.code, exc.read().decode("utf-8", errors="replace")
    except OSError as exc:
        return False, -1, str(exc)


def _scenario_result(
    commit_worktree: Path, plan: dict[str, Any], runner: CommandRunner
) -> tuple[bool, int, str, list[str]]:
    scenario_set_path = plan.get("scenario_set")
    if not isinstance(scenario_set_path, str):
        raise ConfigError("the plan has no scenario set; pass --url or --command")
    scenarios = load_scenario_set(Path(scenario_set_path))
    directory = (Path(scenario_set_path).parent / scenarios.directory).resolve()
    notes: list[str] = []
    output: list[str] = []
    ok = True
    for scenario in scenarios.scenarios:
        result = runner.run(
            scenario.argv(sys.executable, directory),
            commit_worktree,
            env={"PYTHONPATH": str(commit_worktree)},
            timeout_s=scenario.timeout_s,
        )
        notes.append(f"{scenario.id}: {'pass' if result.ok else 'fail'}")
        output.append(result.output)
        ok = ok and result.ok
    combined = "\n".join(output)
    return ok, 0 if ok else 1, combined, notes


def confirm(
    paths: WorksPaths,
    task_id: str,
    *,
    url: str | None = None,
    command: str | list[str] | None = None,
    provider: str = "none",
    tracker: str | None = None,
    close_issue: bool = False,
    force: bool = False,
    runner: CommandRunner | None = None,
    tracker_client: Tracker | None = None,
) -> Confirmation:
    effective_tracker = tracker or provider
    if effective_tracker not in ("none", "github", "gitlab", "jira"):
        raise ConfigError(
            f"unknown tracker {effective_tracker!r}; expected none, github, gitlab or jira"
        )
    queue = Queue(paths)
    task = queue.load(task_id)
    if task.state is not TaskState.RELEASED:
        raise ConfigError(f"task {task_id} is {task.state.value}; confirm runs after release")
    packet = release_packet(paths, task_id)
    if not packet.ready:
        raise ConfigError("confirmation is blocked: " + "; ".join(packet.blockers))
    run_dir = latest_run_dir(paths, task_id)
    if run_dir is None:
        raise ConfigError("the task has no finished run")
    delivery_path = run_dir / "delivery.json"
    if not delivery_path.exists():
        raise ConfigError("the task has not been delivered; run `works deliver` first")
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    commit = str(delivery.get("commit") or "")
    if not commit:
        raise ConfigError("the delivery record names no commit")
    previous = _load(run_dir)
    if previous is not None and previous.get("commit") == commit and not force:
        confirmation = Confirmation(**previous)
        confirmation.created = False
        return confirmation

    repo = GitRepo(Path(task.repo), runner or SubprocessRunner())
    worktree = paths.worktrees / f"{delivery.get('run_id', 'run')}-confirm" / "repo"
    if worktree.exists():
        repo.worktree_remove(worktree)
    repo.worktree_add(worktree, commit)
    command_runner = runner or SubprocessRunner()
    notes: list[str] = []
    output = ""
    target = "scenario set"
    exit_code = 0
    if url is not None:
        target = f"http {url}"
        ok, exit_code, output = _http_check(url)
    elif command is not None:
        target = f"command {command}"
        argv = command if isinstance(command, list) else shlex.split(command, posix=os.name != "nt")
        result: CommandResult = command_runner.run(
            argv, worktree, env={"PYTHONPATH": str(worktree)}, timeout_s=600
        )
        ok, exit_code, output = result.ok, result.exit_code, result.output
    else:
        plan: dict[str, Any] = {}
        for event in queue.events(task_id):
            if event.type == "plan.drafted":
                plan = dict(event.data)
        ok, exit_code, output, scenario_notes = _scenario_result(worktree, plan, command_runner)
        notes.extend(scenario_notes)
        target = f"scenario set ({len(scenario_notes)})"
        if not scenario_notes:
            notes.append("no scenarios ran")
    confirmation = Confirmation(
        task_id=task_id,
        run_id=str(delivery.get("run_id") or ""),
        commit=commit,
        ok=ok,
        target=target,
        exit_code=exit_code,
        output_sha256=hashlib.sha256(output.encode("utf-8", errors="replace")).hexdigest(),
        notes=notes,
    )
    if effective_tracker != "none":
        tracker_obj = tracker_client or build_tracker(effective_tracker)
        if tracker_obj is None:
            raise ConfigError(f"tracker {effective_tracker!r} is not available")
        if not tracker_accepts(effective_tracker, task.source.ref):
            raise ConfigError(f"tracker {effective_tracker!r} cannot return to {task.source.ref!r}")
        body = (
            f"Confirmed `{commit}` with `{target}`: {'pass' if ok else 'fail'}\n\n"
            f"{_source_marker(confirmation.run_id)}"
        )
        confirmation.comment_url = tracker_obj.ensure_comment(
            ref=task.source.ref, body=body, marker=_source_marker(confirmation.run_id)
        )
        if close_issue and ok:
            tracker_obj.close(ref=task.source.ref)
            confirmation.notes.append("source issue closed")
    elif close_issue:
        confirmation.notes.append("no tracker configured; the source issue was not closed")
    (run_dir / "confirmation.json").write_text(
        json.dumps(confirmation.as_dict(), indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    queue.append(task_id, "confirmation.finished", confirmation.as_dict())
    return confirmation
