"""Check that a page's status banner agrees with docs/manifest.yaml.

Non-active pages must carry a banner directly under the H1. Active pages may carry one; if they do,
it must say the same thing. The banner is the reader's warning, so a mismatch is a documentation
bug even when the manifest itself is valid.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "manifest.yaml"
BANNER = re.compile(
    r"^> \*\*Doc status:\*\* (?P<status>[a-z]+) · \*\*Owner:\*\* (?P<owner>.+?) · "
    r"\*\*Last reviewed:\*\* (?P<date>\d{4}-\d{2}-\d{2})\s*$"
)
STATUSES = frozenset({"active", "legacy", "archived", "generated"})
FENCE = re.compile(r"```.*?```", re.DOTALL)
MAX_LINE = 20


def load_documents() -> list[dict[str, Any]]:
    payload = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    documents = payload.get("documents") if isinstance(payload, dict) else None
    if not isinstance(documents, list):
        raise SystemExit(f"{MANIFEST.relative_to(ROOT)}: documents must be a list")
    return [entry for entry in documents if isinstance(entry, dict)]


def as_date(value: Any) -> str:
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)


def main() -> int:
    problems: list[str] = []
    checked = 0
    for entry in load_documents():
        path = entry.get("path")
        if not isinstance(path, str):
            continue
        file = ROOT / path
        if not file.is_file():
            continue
        checked += 1
        text = file.read_text(encoding="utf-8")
        # Keep line numbers stable while ignoring examples inside fenced code blocks.
        text = FENCE.sub(lambda match: "\n" * match.group(0).count("\n"), text)
        lines = text.splitlines()
        found: list[tuple[int, re.Match[str]]] = []
        for index, line in enumerate(lines):
            if not line.startswith("> **Doc status:**"):
                continue
            match = BANNER.fullmatch(line.strip())
            if match is None:
                problems.append(f"{path}:{index + 1}: malformed status banner")
                continue
            found.append((index, match))

        status = entry.get("status")
        if len(found) > 1:
            problems.append(f"{path}: more than one status banner")
        if not found:
            if status != "active":
                problems.append(f"{path}: status {status!r} requires a status banner")
            continue

        index, match = found[0]
        if index > MAX_LINE:
            problems.append(
                f"{path}:{index + 1}: status banner must be within the first {MAX_LINE} lines"
            )
        if match.group("status") not in STATUSES:
            problems.append(f"{path}: banner status {match.group('status')!r} is not recognised")
        if match.group("status") != status:
            problems.append(
                f"{path}: banner status {match.group('status')!r} != manifest status {status!r}"
            )
        if match.group("owner").strip() != str(entry.get("owner")).strip():
            problems.append(f"{path}: banner owner does not match the manifest")
        if match.group("date") != as_date(entry.get("last_reviewed")):
            problems.append(f"{path}: banner date does not match last_reviewed")

    for problem in problems:
        print(problem)
    print(f"docs status: {checked} pages checked, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
