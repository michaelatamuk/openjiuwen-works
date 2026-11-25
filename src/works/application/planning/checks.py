"""Integrity of the check set: the scenario scripts a plan approved are the ones that run."""

from __future__ import annotations

import hashlib
from pathlib import Path

from works.application.execution.scenarios import ScenarioSet


def scenario_digest(directory: Path, scenarios: ScenarioSet) -> str:
    parts: list[str] = []
    for scenario in sorted(scenarios.scenarios, key=lambda item: item.id):
        script = directory / scenario.script
        try:
            digest = hashlib.sha256(script.read_bytes()).hexdigest()
        except OSError:
            digest = "missing"
        parts.append(f"{scenario.id}:{scenario.script}:{digest}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
