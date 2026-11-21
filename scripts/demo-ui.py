"""Build a small, realistic read-only preview for `works ui`.

The demo uses open-source products that people actually use, with human issue titles and spread-out
event times. The blocked task uses a tablet-zoom scenario so the Story view can explain a failure in
plain language.

    python scripts/demo-ui.py
    works --home %TEMP%\\opencode\\works-ui-demo-v4 ui
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from works.config import WorksPaths
from works.evidence import Evidence, write_evidence
from works.gitops import init_repo
from works.harness.fake import FakeHarness
from works.ledger import Ledger
from works.queue import Queue
from works.records import Source, SourceKind, Task
from works.runner import SubprocessRunner
from works.supervisor import Supervisor

FACTORY = Path(__file__).resolve().parents[1]


def _copy_flows(workspace: WorksPaths) -> None:
    shutil.copytree(FACTORY / "flows", workspace.flows)


def _repo(root: Path):
    repo_dir = root / "repo"
    shutil.copytree(FACTORY / "fixtures" / "fixture-repo", repo_dir)
    return init_repo(repo_dir)


def _tablet_scenarios(root: Path) -> Path:
    directory = root / "scenarios"
    scripts = directory / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "tablet_zoom.py").write_text(
        "import sys\n\nprint('The brush cursor still disappears on a tablet after zooming.')\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
        newline="\n",
    )
    path = directory / "tablet-zoom.yaml"
    path.write_text(
        "schema_version: 1\nflow: fix-issue\ndirectory: .\nscenarios:\n"
        "  - id: tablet-zoom-check\n    priority: P0\n    weight: 1.0\n"
        "    description: The brush cursor disappears when zooming on a tablet.\n"
        "    script: scripts/tablet_zoom.py\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _submit(queue: Queue, repo_path: Path, *, ref: str, title: str, product: str, detector: bool) -> Task:
    task, _ = queue.submit(
        source=Source(
            kind=SourceKind.DETECTOR if detector else SourceKind.MANUAL,
            ref=ref,
            title=title,
        ),
        flow="fix-issue",
        product=product,
        repo=str(repo_path),
    )
    return task


def _run(workspace: WorksPaths, queue: Queue, task: Task, trace: str, scenarios: Path) -> None:
    supervisor = Supervisor(
        paths=workspace,
        queue=queue,
        ledger=Ledger(workspace.ledger),
        harness=FakeHarness(FACTORY / "fixtures" / "traces" / trace),
        runner=SubprocessRunner(),
    )
    asyncio.run(supervisor.run(task.id, approve_plan=True, scenario_set=scenarios))


def _backdate(workspace: WorksPaths, queue: Queue, task_id: str, base: datetime, span: timedelta) -> None:
    events_path = workspace.task_dir(task_id) / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line]
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
        path = workspace.task_dir(task_id) / name
        if path.exists():
            path.unlink()
    queue.load(task_id)

    latest: tuple[str, Path] | None = None
    for run_json in workspace.runs.glob("*/run.json"):
        data = json.loads(run_json.read_text(encoding="utf-8"))
        if data.get("task_id") == task_id:
            finished = str(data.get("finished_at", ""))
            if latest is None or finished >= latest[0]:
                latest = (finished, run_json.parent)
    if latest is None:
        return
    run_dir = latest[1]
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(tempfile.gettempdir()) / "opencode" / "works-ui-demo-v4",
    )
    args = parser.parse_args()
    root: Path = args.root.expanduser().resolve()
    if root.exists():
        shutil.rmtree(root)
    workspace = WorksPaths(root).ensure()
    _copy_flows(workspace)
    repo = _repo(root)
    queue = Queue(workspace)
    scenarios = FACTORY / "fixtures" / "scenarios" / "fix-add.yaml"
    tablet = _tablet_scenarios(root)
    now = datetime.now(tz=UTC)

    firefox = _submit(
        queue,
        repo.path,
        ref="FIREFOX-1842",
        title="Passwords are not filled on my bank's login page",
        product="Firefox",
        detector=False,
    )
    _run(workspace, queue, firefox, "fix-add.json", scenarios)
    _backdate(workspace, queue, firefox.id, now - timedelta(hours=9), timedelta(hours=3))

    libreoffice = _submit(
        queue,
        repo.path,
        ref="LIBREOFFICE-5521",
        title="The PDF export cuts off the last column of my table",
        product="LibreOffice",
        detector=False,
    )
    _run(workspace, queue, libreoffice, "fix-add.json", scenarios)
    _backdate(workspace, queue, libreoffice.id, now - timedelta(hours=6), timedelta(hours=2))

    gimp = _submit(
        queue,
        repo.path,
        ref="GIMP-9013",
        title="The brush cursor disappears when I zoom in",
        product="GIMP",
        detector=False,
    )
    _run(workspace, queue, gimp, "fix-add-sneaky.json", tablet)
    _backdate(workspace, queue, gimp.id, now - timedelta(hours=2), timedelta(minutes=45))

    joplin = _submit(
        queue,
        repo.path,
        ref="JOPLIN-3187",
        title="Notes from my phone do not appear on my laptop",
        product="Joplin",
        detector=False,
    )
    _backdate(workspace, queue, joplin.id, now - timedelta(minutes=20), timedelta(minutes=1))

    print(root)
    print("Next: works --home", root, "ui")


if __name__ == "__main__":
    main()
