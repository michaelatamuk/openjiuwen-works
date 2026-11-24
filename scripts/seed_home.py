"""Build a deterministic home for contract fixtures and manual previews.

The home contains a fixture repository, flows, a scenario set and tasks covering queued, planning,
blocked, proved, released and delivered/confirmed states. Timestamps are fixed so repeated runs
produce the same payloads after canonicalization.

    python scripts/seed_home.py --root %TEMP%\\opencode\\works-seed-home
    works --home %TEMP%\\opencode\\works-seed-home ui
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from works.adapters.git.repo import GitRepo, init_repo
from works.adapters.harness.fake import FakeHarness
from works.adapters.processes.runner import SubprocessRunner
from works.adapters.queue.ledger import Ledger
from works.adapters.queue.store import Queue
from works.application.delivery.release import approve_release, latest_run_dir
from works.application.execution.flakes import add_flake
from works.application.supervisor import Supervisor
from works.config.paths import WorksPaths
from works.domain.evidence import Evidence, write_evidence
from works.domain.records import Source, SourceKind, Task, TaskState

FACTORY = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = Path(tempfile.gettempdir()) / "opencode" / "works-seed-home"
DEFAULT_NOW = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)


def _copy_flows(paths: WorksPaths) -> None:
    if not paths.flows.exists():
        shutil.copytree(FACTORY / "flows", paths.flows)


def _repo(root: Path) -> GitRepo:
    repo_dir = root / "repo"
    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    shutil.copytree(FACTORY / "fixtures" / "fixture-repo", repo_dir)
    return init_repo(repo_dir)


def _scenario_set(root: Path) -> Path:
    source = FACTORY / "fixtures" / "scenarios"
    target = root / "scenarios"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return target / "fix-add.yaml"


def _submit(queue: Queue, repo: Path, *, ref: str, title: str, product: str) -> Task:
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref=ref, title=title),
        flow="fix-issue",
        product=product,
        repo=str(repo),
    )
    return task


def _run(
    paths: WorksPaths,
    queue: Queue,
    task: Task,
    trace: str,
    scenarios: Path,
    *,
    approve_plan: bool = True,
) -> None:
    supervisor = Supervisor(
        paths=paths,
        queue=queue,
        ledger=Ledger(paths.ledger),
        harness=FakeHarness(FACTORY / "fixtures" / "traces" / trace),
        runner=SubprocessRunner(),
    )
    asyncio.run(supervisor.run(task.id, approve_plan=approve_plan, scenario_set=scenarios))


def _move(queue: Queue, task_id: str, target: TaskState) -> None:
    current = queue.load(task_id)
    queue.append(
        task_id,
        "state.changed",
        {"from": current.state.value, "to": target.value},
    )


def _to_planning(queue: Queue, task: Task, scenarios: Path, repo: GitRepo, now: datetime) -> None:
    _move(queue, task.id, TaskState.REPRODUCING)
    queue.append(task.id, "step.started", {"step": "reproduce"})
    queue.append(task.id, "step.finished", {"step": "reproduce", "exit_code": 1})
    _move(queue, task.id, TaskState.REPRODUCED)
    _move(queue, task.id, TaskState.PLANNING)
    queue.append(
        task.id,
        "plan.drafted",
        {
            "plan_id": f"p-{task.id}-v1",
            "version": 1,
            "hash": "a" * 64,
            "status": "validated",
            "base_commit": repo.head(),
            "checks_sha": "b" * 64,
            "checks_source": "workspace",
            "scenario_set": str(scenarios),
            "scenario_ids": ["add-negative"],
            "p0": ["add-negative"],
            "p1": [],
            "nodes": ["reproduce", "build", "test"],
            "summary": "Fix addition and cover the negative case.",
            "validation": {"ok": True, "errors": [], "warnings": []},
            "provenance": {
                "planner": "deterministic",
                "provider": None,
                "model": None,
                "tokens": 0,
                "usd": 0.0,
                "duration_ms": 0,
            },
            "brief": "Summary: Fix addition and cover the negative case.",
        },
    )
    _backdate(queue, task.id, now - timedelta(minutes=20), timedelta(minutes=8))


def _delivery(paths: WorksPaths, queue: Queue, task: Task, now: datetime) -> None:
    _, packet, _ = approve_release(paths, task.id, by="cli")
    run_dir = latest_run_dir(paths, task.id)
    if run_dir is None or not packet.commit:
        raise SystemExit(f"cannot deliver {task.id}: no run or commit")
    delivery = {
        "task_id": task.id,
        "run_id": run_dir.name,
        "commit": packet.commit,
        "branch": "works/seed-delivered",
        "provider": "github",
        "tracker": "github",
        "pr_url": "https://example.test/pull/7",
        "comment_url": "https://example.test/issues/7#comment",
        "pushed": True,
        "dry_run": False,
        "created": True,
        "notes": ["pull request: https://example.test/pull/7"],
    }
    (run_dir / "delivery.json").write_text(
        json.dumps(delivery, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    queue.append(task.id, "delivery.finished", delivery)
    confirmation = {
        "task_id": task.id,
        "run_id": run_dir.name,
        "commit": packet.commit,
        "ok": True,
        "target": "https://example.test/health",
        "exit_code": 0,
        "duration_ms": 120,
        "output_sha256": "c" * 64,
        "url": "https://example.test/health",
        "command": None,
        "screenshots": [],
        "notes": [],
        "comment_url": None,
        "created": True,
    }
    (run_dir / "confirmation.json").write_text(
        json.dumps(confirmation, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    queue.append(task.id, "confirmation.finished", confirmation)
    deployment = {
        "task_id": task.id,
        "run_id": run_dir.name,
        "commit": packet.commit,
        "environment": "staging",
        "command": ["python", "-m", "deploy", "--staging"],
        "status": "deployed",
        "exit_code": 0,
        "output_tail": "ok",
        "dry_run": False,
        "created": True,
        "notes": [],
        "started_at": (now - timedelta(minutes=2)).isoformat(),
        "finished_at": (now - timedelta(minutes=1)).isoformat(),
    }
    (run_dir / "deployment.json").write_text(
        json.dumps(deployment, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    queue.append(task.id, "deploy.finished", deployment)


def _backdate(queue: Queue, task_id: str, base: datetime, span: timedelta) -> None:
    paths = queue.paths
    events_path = paths.task_dir(task_id) / "events.jsonl"
    events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    step = span / max(1, len(events) - 1)
    moments = [base + step * index for index in range(len(events))]
    for event, moment in zip(events, moments, strict=True):
        event["ts"] = moment.isoformat()
        if event.get("type") == "task.created":
            payload = event.get("data", {}).get("task")
            if isinstance(payload, dict):
                payload["created_at"] = moment.isoformat()
                payload["updated_at"] = moment.isoformat()
    events_path.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    for name in ("task.yaml", "task.json"):
        (paths.task_dir(task_id) / name).unlink(missing_ok=True)
    queue.load(task_id)

    run_dir = latest_run_dir(paths, task_id)
    if run_dir is None:
        return
    duration_ms = int(span.total_seconds() * 1000)
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    run["started_at"] = base.isoformat()
    run["finished_at"] = moments[-1].isoformat()
    run["duration_ms"] = duration_ms
    (run_dir / "run.json").write_text(
        json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    evidence_path = run_dir / "evidence.json"
    if evidence_path.exists():
        evidence = Evidence.model_validate_json(evidence_path.read_text(encoding="utf-8"))
        write_evidence(run_dir, evidence.model_copy(update={"duration_ms": duration_ms}).bind())


def seed(root: Path, *, now: datetime = DEFAULT_NOW) -> WorksPaths:
    """Create the deterministic home. The caller owns cleanup."""
    paths = WorksPaths(root).ensure()
    _copy_flows(paths)
    repo = _repo(root)
    scenarios = _scenario_set(root)
    queue = Queue(paths)

    queued = _submit(
        queue, repo.path, ref="SEED-QUEUED-1", title="A queued report", product="Fixture"
    )

    planning = _submit(
        queue,
        repo.path,
        ref="SEED-PLANNING-1",
        title="A plan waiting for approval",
        product="Fixture",
    )
    _to_planning(queue, planning, scenarios, repo, now)

    proved = _submit(queue, repo.path, ref="SEED-PROVED-1", title="A proved fix", product="Fixture")
    _run(paths, queue, proved, "fix-add.json", scenarios)
    _backdate(queue, proved.id, now - timedelta(hours=3), timedelta(hours=1))

    released = _submit(
        queue,
        repo.path,
        ref="SEED-RELEASED-1",
        title="A released and delivered fix",
        product="Fixture",
    )
    _run(paths, queue, released, "fix-add.json", scenarios)
    _delivery(paths, queue, released, now - timedelta(hours=2))
    _backdate(queue, released.id, now - timedelta(hours=2), timedelta(hours=1, minutes=10))

    blocked = _submit(
        queue,
        repo.path,
        ref="SEED-BLOCKED-1",
        title="A change that touches tests",
        product="Fixture",
    )
    _run(paths, queue, blocked, "fix-add-sneaky.json", scenarios)
    _backdate(queue, blocked.id, now - timedelta(minutes=45), timedelta(minutes=20))

    add_flake(
        paths,
        task_id=proved.id,
        scenario_id="add-negative",
        owner="owner@example.test",
        reason="timing",
        now=now - timedelta(hours=1),
    )

    if queued.state is not TaskState.QUEUED:
        raise SystemExit(f"queued task is {queued.state.value}")
    return paths


def _clean(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--now", default=DEFAULT_NOW.isoformat())
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if root.exists() and not args.force:
        raise SystemExit(f"{root} exists; pass --force to replace it")
    _clean(root)
    now = datetime.fromisoformat(args.now)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    seed(root, now=now)
    print(root)
    print("Next: works --home", root, "ui")


if __name__ == "__main__":
    main()
