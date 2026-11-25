"""Static impact: which tests cover the files a report names?

No model and no call graph. The report's text names paths (a stack trace usually does), the test
files import modules or mention paths, and the intersection becomes the must-pass list. Anything
named but uncovered is recorded as a gap instead of being hidden.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

PATH = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+\.(?:py|ts|tsx|js|go|rs|java))")
TEST_NAMES = re.compile(r"(^|/)(?:test_[^/]*\.py|[^/]*_test\.py)$")


def named_paths(text: str) -> list[str]:
    found: list[str] = []
    for match in PATH.finditer(text or ""):
        path = match.group(1).lstrip("./")
        if path and path not in found:
            found.append(path)
    return found


def _module(path: str) -> str:
    clean = path.replace("\\", "/")
    if clean.endswith(".py"):
        clean = clean[:-3]
    parts = [part for part in clean.split("/") if part and part != "__init__"]
    return ".".join(parts)


def _imports(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def tests_for(repo: Path, paths: list[str], *, limit: int = 400) -> dict[str, list[str]]:
    """Map each named path to test files that import its module or mention the path."""
    wanted = {_module(path): path for path in paths}
    found: dict[str, list[str]] = {path: [] for path in paths}
    if not wanted:
        return found
    scanned = 0
    for candidate in sorted(repo.rglob("test_*.py")) + sorted(repo.rglob("*_test.py")):
        if scanned >= limit:
            break
        if any(part in {".git", ".venv", "node_modules"} for part in candidate.parts):
            continue
        scanned += 1
        try:
            source = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        relative = candidate.relative_to(repo).as_posix()
        imports = _imports(source)
        for module, original in wanted.items():
            if (
                module in imports
                or any(
                    module.startswith(name + ".") or name.startswith(module + ".")
                    for name in imports
                )
                or original in source
            ):
                found[original].append(relative)
    return found


def describe(repo: Path, text: str) -> tuple[list[str], list[str]]:
    """Return (verification lines, uncovered gaps) for the paths named in the text."""
    paths = named_paths(text)
    if not paths:
        return [], []
    mapping = tests_for(repo, paths)
    lines: list[str] = []
    gaps: list[str] = []
    for path, tests in mapping.items():
        if tests:
            lines.append(f"Impact: {path} is covered by {', '.join(tests)}.")
        else:
            gaps.append(path)
    return lines, gaps
