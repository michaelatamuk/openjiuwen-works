"""Readiness: may this repository be automated at all?

The gate is deliberately boring: it runs the commands the repository declares in
`.works/readiness.yaml`, finds unapproved suppressions and requires a feature map. A red gate is a
refusal, not a warning; the caller decides whether to block an autonomous run.
"""

from __future__ import annotations

import ast
import io
import re
import shlex
import subprocess  # nosec B404
import sys
import time
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from works.application.observability.features import feature_files as mapped_feature_files
from works.application.observability.features import load_feature_maps
from works.domain.errors import ConfigError, PolicyError

CheckStatus = Literal["pass", "fail", "skip"]
ReportStatus = Literal["pass", "fail", "partial"]

SPEC_PATH = Path(".works/readiness.yaml")
COMMANDS = (
    ("lint", "Lint"),
    ("format", "Format"),
    ("types", "Types"),
    ("tests", "Fast tests"),
    ("verify", "Product verify"),
    ("architecture", "Architecture boundaries"),
)
_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "runs",
    "queue",
    "worktrees",
    "dist",
    "build",
}
_SUPPRESSION_PATTERNS = (
    ("noqa", re.compile(r"#\s*noqa\b", re.IGNORECASE)),
    ("type-ignore", re.compile(r"#\s*type:\s*ignore\b", re.IGNORECASE)),
    ("skip", re.compile(r"pytest\.mark\.skip(?:if)?\b")),
    ("xfail", re.compile(r"pytest\.mark\.xfail\b")),
)


class Commands(BaseModel):
    lint: str | None = None
    format: str | None = None
    types: str | None = None
    tests: str | None = None
    verify: str | None = None
    architecture: str | None = None


class Suppressions(BaseModel):
    allow: list[str] = Field(default_factory=list)


class BoundaryRule(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(alias="from", min_length=1)
    deny: list[str] = Field(default_factory=list)


class Boundaries(BaseModel):
    rules: list[BoundaryRule] = Field(default_factory=list)


class ReadinessSpec(BaseModel):
    schema_version: int = 1
    features: str = "features"
    commands: Commands = Field(default_factory=Commands)
    suppressions: Suppressions = Field(default_factory=Suppressions)
    boundaries: Boundaries = Field(default_factory=Boundaries)


@dataclass(frozen=True)
class CheckResult:
    id: str
    label: str
    status: CheckStatus
    detail: str = ""

    @property
    def ok(self) -> bool | None:
        if self.status == "skip":
            return None
        return self.status == "pass"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "ok": self.ok,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SuppressionFinding:
    location: str
    kind: str
    text: str

    def as_dict(self) -> dict[str, str]:
        return {"location": self.location, "kind": self.kind, "text": self.text}


@dataclass
class ReadinessReport:
    status: ReportStatus
    checks: list[CheckResult]
    passed: int
    failed: int
    skipped: int
    total: int
    suppressions: list[SuppressionFinding] = field(default_factory=list)
    unknown_suppressions: list[SuppressionFinding] = field(default_factory=list)
    feature_files: list[str] = field(default_factory=list)
    import_cycles: list[list[str]] = field(default_factory=list)
    import_edges: dict[str, list[str]] = field(default_factory=dict)
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": True,
            "status": self.status,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "total": self.total,
            "checks": [check.as_dict() for check in self.checks],
            "suppressions": [item.as_dict() for item in self.suppressions],
            "unknown_suppressions": [item.as_dict() for item in self.unknown_suppressions],
            "features": self.feature_files,
            "import_cycles": self.import_cycles,
            "import_edges": self.import_edges,
            "note": self.note,
        }


def load_spec(repo: Path) -> ReadinessSpec | None:
    path = repo / SPEC_PATH
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read {SPEC_PATH}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{SPEC_PATH} must be a mapping")
    try:
        return ReadinessSpec.model_validate(raw)
    except Exception as exc:
        raise ConfigError(f"{SPEC_PATH} is invalid: {exc}") from exc


def _iter_python_files(repo: Path) -> Iterator[tuple[Path, Path]]:
    for path in repo.rglob("*.py"):
        relative = path.relative_to(repo)
        if any(part in _SKIP_DIRS for part in relative.parts):
            continue
        yield path, relative


def _comments(path: Path, text: str) -> dict[int, str]:
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        return {token.start[0]: token.string for token in tokens if token.type == tokenize.COMMENT}
    except (tokenize.TokenError, IndentationError):
        return {}


def find_suppressions(repo: Path) -> list[SuppressionFinding]:
    found: list[SuppressionFinding] = []
    seen: set[str] = set()
    for path, relative in _iter_python_files(repo):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        comments = _comments(path, text)
        for number, line in enumerate(text.splitlines(), start=1):
            comment = comments.get(number, "")
            for kind, pattern in _SUPPRESSION_PATTERNS:
                haystack = comment if kind in ("noqa", "type-ignore") else line
                if not pattern.search(haystack):
                    continue
                location = f"{relative.as_posix()}:{number}:{kind}"
                if location in seen:
                    continue
                seen.add(location)
                found.append(
                    SuppressionFinding(
                        location=location,
                        kind=kind,
                        text=line.strip()[:200],
                    )
                )
    return found


def _module_name(repo: Path, path: Path) -> str:
    relative = path.relative_to(repo)
    parts = list(relative.with_suffix("").parts)
    if parts and parts[0] in ("src", "lib"):
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def import_violations(repo: Path, rules: list[BoundaryRule]) -> list[str]:
    if not rules:
        return []
    violations: list[str] = []
    for path, _relative in _iter_python_files(repo):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        module = _module_name(repo, path)
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.append(node.module)
        for rule in rules:
            if not module.startswith(rule.source):
                continue
            for name in imported:
                if any(name == denied or name.startswith(f"{denied}.") for denied in rule.deny):
                    violations.append(f"{module} imports {name} (denied by {rule.source})")
    return sorted(set(violations))


def _find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    state: dict[str, int] = {}
    stack: list[str] = []
    found: set[tuple[str, ...]] = set()

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for target in graph.get(node, []):
            if state.get(target) == 1:
                start = stack.index(target)
                found.add((*stack[start:], target))
            elif state.get(target, 0) == 0:
                visit(target)
        stack.pop()
        state[node] = 2

    for node in sorted(graph):
        if state.get(node, 0) == 0:
            visit(node)
    return [list(cycle) for cycle in sorted(found)]


def import_graph(repo: Path) -> tuple[dict[str, list[str]], list[list[str]]]:
    modules: dict[str, list[str]] = {}
    for path, _relative in _iter_python_files(repo):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imports.append(node.module)
        modules[_module_name(repo, path)] = imports
    internal = set(modules)
    graph = {
        module: sorted({name for name in imports if name in internal})
        for module, imports in modules.items()
    }
    return graph, _find_cycles(graph)


def _run_command(repo: Path, command: str, timeout_s: int) -> CheckResult:
    argv = [sys.executable if part == "{python}" else part for part in shlex.split(command)]
    started = time.monotonic()
    try:
        completed = subprocess.run(  # nosec B603
            argv,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CheckResult("command", "Command", "fail", f"timed out after {timeout_s}s")
    except OSError as exc:
        return CheckResult("command", "Command", "fail", f"could not start: {exc}")
    duration = int((time.monotonic() - started) * 1000)
    output = (completed.stderr or completed.stdout or "").strip().splitlines()
    tail = " · ".join(output[-3:])[:500]
    detail = f"exit {completed.returncode} in {duration} ms" + (f": {tail}" if tail else "")
    return CheckResult(
        "command", "Command", "pass" if completed.returncode == 0 else "fail", detail
    )


def assess(
    repo: Path,
    *,
    run_commands: bool = True,
    timeout_s: int = 120,
) -> ReadinessReport:
    repo = repo.resolve()
    spec = load_spec(repo)
    checks: list[CheckResult] = []

    checks.append(
        CheckResult(
            "git",
            "Git repository",
            "pass" if (repo / ".git").exists() else "fail",
            ".git found" if (repo / ".git").exists() else "not a git repository",
        )
    )
    project = next(
        (
            name
            for name in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod")
            if (repo / name).exists()
        ),
        None,
    )
    checks.append(
        CheckResult(
            "project",
            "Project manifest",
            "pass" if project else "fail",
            project or "no pyproject/package/Cargo/go module",
        )
    )

    feature_root = spec.features if spec is not None else "features"
    features = [path.name for path in mapped_feature_files(repo, feature_root)]
    try:
        maps = load_feature_maps(repo, feature_root)
    except ConfigError as exc:
        feature_check = CheckResult("features", "Feature map", "fail", str(exc))
    else:
        count = sum(len(feature_map.features) for feature_map in maps)
        feature_check = CheckResult(
            "features",
            "Feature map",
            "pass" if count else "fail",
            f"{count} feature(s) in {len(features)} file(s)" if count else "no features declared",
        )
    checks.append(feature_check)

    suppressions = find_suppressions(repo)
    allow = set(spec.suppressions.allow) if spec is not None else set()
    unknown = [item for item in suppressions if item.location not in allow]
    checks.append(
        CheckResult(
            "suppressions",
            "Known suppressions",
            "pass" if not unknown else "fail",
            f"{len(suppressions)} found, {len(unknown)} unknown" if suppressions else "none found",
        )
    )

    rules = spec.boundaries.rules if spec is not None else []
    violations = import_violations(repo, rules)
    checks.append(
        CheckResult(
            "imports",
            "Import boundaries",
            "pass" if not violations else "fail",
            f"{len(violations)} violation(s)" if violations else f"{len(rules)} rule(s)",
        )
    )

    graph, cycles = import_graph(repo)
    checks.append(
        CheckResult(
            "cycles",
            "Import cycles",
            "pass" if not cycles else "fail",
            f"{len(cycles)} cycle(s)" if cycles else f"{len(graph)} module(s)",
        )
    )

    commands = spec.commands if spec is not None else Commands()
    for command_id, label in COMMANDS:
        command = getattr(commands, command_id)
        if not run_commands:
            checks.append(
                CheckResult(
                    command_id,
                    label,
                    "skip",
                    "not run in the preview; run `works readiness`",
                )
            )
            continue
        if not command:
            checks.append(
                CheckResult(
                    command_id,
                    label,
                    "fail",
                    f"not configured in {SPEC_PATH.as_posix()}",
                )
            )
            continue
        result = _run_command(repo, command, timeout_s)
        checks.append(CheckResult(command_id, label, result.status, result.detail))

    passed = sum(1 for check in checks if check.status == "pass")
    failed = sum(1 for check in checks if check.status == "fail")
    skipped = sum(1 for check in checks if check.status == "skip")
    total = len(checks)
    if failed:
        status: ReportStatus = "fail"
        note = "Red gate: automation must not start until every check is green."
    elif skipped:
        status = "partial"
        note = "Static checks only; run `works readiness` to execute the configured commands."
    else:
        status = "pass"
        note = "Green: the repository is ready for autonomous work."
    if spec is None:
        note = f"No {SPEC_PATH.as_posix()} found. Add one before autonomy."
    return ReadinessReport(
        status=status,
        checks=checks,
        passed=passed,
        failed=failed,
        skipped=skipped,
        total=total,
        suppressions=suppressions,
        unknown_suppressions=unknown,
        feature_files=features,
        import_cycles=cycles,
        import_edges=graph,
        note=note,
    )


def ensure_ready(repo: Path, *, timeout_s: int = 120) -> ReadinessReport:
    """Run the full gate; a red report is a refusal, not a warning."""
    report = assess(repo, run_commands=True, timeout_s=timeout_s)
    if report.status == "fail":
        failed = ", ".join(check.id for check in report.checks if check.status == "fail")
        raise PolicyError(f"readiness is red ({failed}); run `works readiness` before automation")
    return report
