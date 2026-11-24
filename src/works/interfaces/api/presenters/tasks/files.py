"""Read models from the run directories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from works.config.paths import WorksPaths
from works.domain.records import Event


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _latest(events: list[Event], kind: str) -> Event | None:
    found: Event | None = None
    for event in events:
        if event.type == kind:
            found = event
    return found


def _run_index(paths: WorksPaths) -> dict[str, tuple[str, Path]]:
    """Map task id to its newest run directory."""
    index: dict[str, tuple[str, Path]] = {}
    if not paths.runs.exists():
        return index
    for run_json in paths.runs.glob("*/run.json"):
        data = _read_json(run_json)
        if not isinstance(data, dict):
            continue
        task_id = data.get("task_id")
        finished = str(data.get("finished_at", ""))
        if not isinstance(task_id, str):
            continue
        previous = index.get(task_id)
        if previous is None or finished >= previous[0]:
            index[task_id] = (finished, run_json.parent)
    return index


def readiness(repo: Path) -> dict[str, Any]:
    from works.application.execution.readiness import assess

    return assess(repo, run_commands=False).as_dict()


def feature_map(repo: Path, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    from works.application.observability.features import feature_summary

    return feature_summary(repo, evidence)
