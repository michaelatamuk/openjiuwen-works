"""Path policy. Data, not a prompt. Deny wins, test paths are denied by default."""

from __future__ import annotations

import ast
import re
import unicodedata

from pydantic import BaseModel, Field

from works.domain.flow import PathsSpec

DEFAULT_DENY: tuple[str, ...] = (
    "**/test_*.py",
    "**/*_test.py",
    "**/tests/",
    "**/conftest.py",
    "**/pytest.ini",
    "**/tox.ini",
    "**/migrations/",
    "**/scenarios/",
    "**/.github/",
    "**/quarantine.json",
)

_CONTROL = tuple(chr(code) for code in range(32))


class Violation(BaseModel):
    path: str
    reason: str


class PolicyReport(BaseModel):
    schema_version: int = 1
    ok: bool
    violations: list[Violation] = Field(default_factory=list)


def normalize_path(raw: str) -> str:
    """NFC, forward slashes, no empty or dot segments, no trailing dots/spaces."""
    text = unicodedata.normalize("NFC", raw).replace("\\", "/").strip()
    parts: list[str] = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            parts.append(part)
            continue
        cleaned = part.rstrip(" .")
        if cleaned:
            parts.append(cleaned)
    return "/".join(parts)


def is_unsafe(raw: str) -> bool:
    text = unicodedata.normalize("NFC", raw).replace("\\", "/")
    if not text.strip():
        return True
    if any(ch in text for ch in _CONTROL):
        return True
    if '"' in text:
        return True
    if text.startswith("/") or text.startswith("~"):
        return True
    if len(text) > 1 and text[1] == ":":
        return True
    return any(part == ".." for part in text.split("/"))


def _glob(path: str, pattern: str) -> bool:
    from fnmatch import fnmatch

    lowered_path = path.lower()
    lowered_pattern = pattern.lower()
    if fnmatch(lowered_path, lowered_pattern):
        return True
    if lowered_pattern.startswith("**/"):
        return fnmatch(lowered_path, lowered_pattern[3:])
    return False


def _directory(path: str, pattern: str) -> bool:
    raw = pattern[3:] if pattern.startswith("**/") else pattern
    name = raw.rstrip("/").lower()
    if not name:
        return False
    lowered = path.lower()
    if lowered == name or lowered.startswith(name + "/"):
        return True
    return f"/{name}/" in f"/{lowered}/"


def matches(path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    return any(_glob(path, p) or _directory(path, p) for p in patterns)


def check_paths(paths: list[str], spec: PathsSpec) -> list[Violation]:
    """Deny wins. Test paths are denied unless a flow explicitly says otherwise."""
    deny = tuple(DEFAULT_DENY) + tuple(spec.deny)
    violations: list[Violation] = []
    for raw in paths:
        if is_unsafe(raw):
            violations.append(Violation(path=raw, reason="unsafe path (absolute, drive or ..)"))
            continue
        path = normalize_path(raw)
        if not path:
            violations.append(Violation(path=raw, reason="empty path"))
        elif matches(path, deny):
            violations.append(Violation(path=path, reason="denied by policy"))
        elif spec.allow and not matches(path, spec.allow):
            violations.append(Violation(path=path, reason="not in the allow list"))
    return violations


_DIFF_GIT = re.compile(r'^diff --git (?P<a>"(?:\\.|[^"])*"|\S+) (?P<b>"(?:\\.|[^"])*"|\S+)$')


def _unquote(raw: str) -> str:
    text = raw.strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        try:
            return str(ast.literal_eval(text))
        except (ValueError, SyntaxError):
            return text
    return text


def paths_from_patch(patch: str) -> list[str]:
    """Every path a unified diff would touch, including renames, deletes and quoted paths."""
    seen: list[str] = []
    for line in patch.splitlines():
        candidate: str | None = None
        header = _DIFF_GIT.match(line)
        if header is not None:
            candidate = _unquote(header.group("b"))
            if candidate.startswith("b/"):
                candidate = candidate[2:]
        elif line.startswith("+++ ") or line.startswith("--- "):
            candidate = _unquote(line[4:].split("\t", 1)[0])
            if candidate in ("/dev/null", ""):
                candidate = None
            elif candidate.startswith(("a/", "b/")):
                candidate = candidate[2:]
        if candidate and candidate not in seen:
            seen.append(candidate)
    return seen


def check_patch(patch: str, spec: PathsSpec) -> list[Violation]:
    return check_paths(paths_from_patch(patch), spec)
