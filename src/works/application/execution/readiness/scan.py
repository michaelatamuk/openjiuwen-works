"""Readiness gate internals.

The public API is re-exported from the package ``__init__`` so callers keep using
``works.application.execution.readiness``.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterator
from pathlib import Path

from works.application.execution.readiness.spec import BoundaryRule, SuppressionFinding

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
