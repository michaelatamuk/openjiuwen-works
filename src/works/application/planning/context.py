"""Bounded planner input and repository context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from works.application.execution.scenarios import ScenarioSet
from works.domain.flow import FlowSpec
from works.domain.plan import PlanProposal, PlanProvenance


@dataclass(frozen=True)
class PlannerContext:
    """The bounded, reproducible input to a planner."""

    task_id: str
    product: str
    task_kind: str
    source_ref: str
    source_title: str
    flow: FlowSpec
    base_commit: str
    checks_sha: str
    checks_source: str
    scenario_set: Path
    scenarios: ScenarioSet
    repo: Path
    budget_tokens: int
    budget_usd: float
    memory: tuple[str, ...] = ()
    prior_plans: tuple[dict[str, Any], ...] = ()
    findings: tuple[str, ...] = ()
    file_tree: tuple[str, ...] = ()
    manifests: tuple[tuple[str, str], ...] = ()
    readme: str = ""

    @property
    def p0_ids(self) -> list[str]:
        return list(self.scenarios.p0_ids)

    @property
    def p1_ids(self) -> list[str]:
        return list(self.scenarios.p1_ids)


@dataclass(frozen=True)
class PlannerOutput:
    proposal: PlanProposal
    provenance: PlanProvenance


@dataclass(frozen=True)
class RepositoryContext:
    file_tree: tuple[str, ...] = ()
    manifests: tuple[tuple[str, str], ...] = ()
    readme: str = ""


_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".hypothesis",
        "dist",
        "build",
        "target",
        "runs",
        "queue",
        "worktrees",
        "logs",
    }
)


_MANIFESTS = ("pyproject.toml", "package.json", "Cargo.toml", "go.mod", "requirements.txt")


def collect_repository_context(repo: Path, *, limit: int = 400) -> RepositoryContext:
    """A bounded, deterministic view of the repository for a planner prompt."""
    files: list[str] = []
    if repo.exists():
        for path in sorted(repo.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(repo)
            if any(part in _SKIP_DIRS for part in relative.parts):
                continue
            files.append(relative.as_posix())
            if len(files) >= limit:
                break
    manifests: list[tuple[str, str]] = []
    for name in _MANIFESTS:
        path = repo / name
        if path.is_file():
            manifests.append((name, _read_bounded(path)))
    readme = ""
    for name in ("README.md", "README.rst", "README.txt"):
        path = repo / name
        if path.is_file():
            readme = _read_bounded(path)
            break
    return RepositoryContext(file_tree=tuple(files), manifests=tuple(manifests), readme=readme)


def _read_bounded(path: Path, limit: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def context_payload(context: PlannerContext) -> dict[str, Any]:
    return {
        "task_id": context.task_id,
        "product": context.product,
        "task_kind": context.task_kind,
        "source": {"ref": context.source_ref, "title": context.source_title},
        "flow": {
            "name": context.flow.flow,
            "nodes": [
                {
                    "id": node.id,
                    "kind": node.kind.value,
                    "required": node.required,
                    "mode": node.mode.value,
                    "cmd": node.cmd,
                }
                for node in context.flow.nodes
            ],
            "gates": [gate.model_dump(mode="json") for gate in context.flow.gates],
            "paths": context.flow.paths.model_dump(mode="json"),
            "budget": context.flow.budget.model_dump(mode="json"),
        },
        "base_commit": context.base_commit,
        "checks_sha": context.checks_sha,
        "checks_source": context.checks_source,
        "scenario_set": str(context.scenario_set),
        "scenarios": [
            {
                "id": scenario.id,
                "priority": scenario.priority.value,
                "description": scenario.description,
                "weight": scenario.weight,
            }
            for scenario in context.scenarios.scenarios
        ],
        "file_tree": list(context.file_tree),
        "manifests": [{"path": path, "content": text} for path, text in context.manifests],
        "readme": context.readme,
        "memory": list(context.memory),
        "prior_plans": list(context.prior_plans),
        "findings": list(context.findings),
        "budget": {"tokens": context.budget_tokens, "usd": context.budget_usd},
    }
