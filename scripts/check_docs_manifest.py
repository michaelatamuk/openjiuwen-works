"""Check that every documentation page is registered in docs/manifest.yaml.

ADRs have their own index (docs/adrs/README.md), the read-only archive is exempt by design, and
the generated JSON is documented by docs/reference/generated/README.md. Everything else must have
one entry with the right title, status, owner, review date, audience and canonical flag.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "manifest.yaml"
DOCS = ROOT / "docs"

STATUSES = frozenset({"active", "legacy", "archived", "generated"})
AUDIENCES = frozenset({"everyone", "user", "operator", "integrator", "engineer", "product"})
REQUIRED = ("path", "title", "status", "owner", "last_reviewed", "audience", "canonical")
EXEMPT_PREFIXES = ("docs/adrs/", "docs/archive/")


def fail(problems: list[str], message: str) -> None:
    problems.append(message)


def h1(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def tracked_pages() -> set[str]:
    pages: set[str] = set()
    for path in sorted(DOCS.rglob("*.md")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(EXEMPT_PREFIXES):
            continue
        pages.add(rel)
    return pages


def load_documents(problems: list[str]) -> list[dict[str, Any]]:
    if not MANIFEST.exists():
        fail(problems, f"{MANIFEST.relative_to(ROOT)}: missing")
        return []
    try:
        payload = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        fail(problems, f"{MANIFEST.relative_to(ROOT)}: invalid YAML: {exc}")
        return []
    if not isinstance(payload, dict):
        fail(problems, f"{MANIFEST.relative_to(ROOT)}: expected a mapping")
        return []
    if payload.get("version") != 1:
        fail(problems, f"{MANIFEST.relative_to(ROOT)}: version must be 1")
    documents = payload.get("documents")
    if not isinstance(documents, list):
        fail(problems, f"{MANIFEST.relative_to(ROOT)}: documents must be a list")
        return []
    return [entry for entry in documents if isinstance(entry, dict)]


def check_entry(entry: dict[str, Any], problems: list[str]) -> str | None:
    missing = [key for key in REQUIRED if key not in entry]
    if missing:
        fail(problems, f"{entry.get('path', '<unknown>')}: missing field(s) {', '.join(missing)}")
        return None

    raw_path = entry["path"]
    if not isinstance(raw_path, str) or not raw_path.startswith("docs/"):
        fail(problems, f"{raw_path!r}: path must be relative and start with docs/")
        return None
    path = Path(raw_path)
    if path.is_absolute() or ".." in path.parts or path.suffix != ".md":
        fail(problems, f"{raw_path}: path must be a relative Markdown file under docs/")
        return None
    if not (ROOT / path).is_file():
        fail(problems, f"{raw_path}: file does not exist")
        return None

    status = entry["status"]
    if status not in STATUSES:
        fail(problems, f"{raw_path}: status {status!r} is not one of {sorted(STATUSES)}")
    audience = entry["audience"]
    if audience not in AUDIENCES:
        fail(problems, f"{raw_path}: audience {audience!r} is not one of {sorted(AUDIENCES)}")
    if not isinstance(entry["owner"], str) or not entry["owner"].strip():
        fail(problems, f"{raw_path}: owner must be a non-empty string")
    if not isinstance(entry["canonical"], bool):
        fail(problems, f"{raw_path}: canonical must be true or false")

    reviewed = entry["last_reviewed"]
    if isinstance(reviewed, dt.date):
        reviewed_date = reviewed
    else:
        try:
            reviewed_date = dt.date.fromisoformat(str(reviewed))
        except ValueError:
            fail(problems, f"{raw_path}: last_reviewed must be YYYY-MM-DD")
            reviewed_date = None
    if reviewed_date is not None and reviewed_date > dt.datetime.now(dt.UTC).date():
        fail(problems, f"{raw_path}: last_reviewed {reviewed_date} is in the future")

    expected_title = h1(ROOT / path)
    if expected_title is None:
        fail(problems, f"{raw_path}: no H1 heading")
    elif entry["title"] != expected_title:
        fail(
            problems,
            f"{raw_path}: title {entry['title']!r} does not match H1 {expected_title!r}",
        )
    return raw_path


def main() -> int:
    problems: list[str] = []
    documents = load_documents(problems)
    listed: dict[str, dict[str, Any]] = {}
    for entry in documents:
        path = check_entry(entry, problems)
        if path is None:
            continue
        if path in listed:
            fail(problems, f"{path}: listed more than once")
        listed[path] = entry

    tracked = tracked_pages()
    for path in sorted(tracked - set(listed)):
        fail(problems, f"{path}: not listed in docs/manifest.yaml")
    for path in sorted(set(listed) - tracked):
        fail(problems, f"{path}: listed but is not a tracked page")

    for problem in problems:
        print(problem)
    print(f"docs manifest: {len(listed)} pages registered, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
