"""Check that docs/design/adrs/README.md indexes every ADR exactly once, in order.

The ADR files use three historical heading styles and two status styles. The index normalises
both: the number comes from the heading, and the status is the first clause before a date or a
delivery note. A record may be superseded, but never deleted or silently unlisted.
"""

from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = ROOT / "docs" / "design" / "adrs"
INDEX = ADR_DIR / "README.md"

H1 = re.compile(r"^# (?:ADR[- ]?)?(?P<num>\d{1,3})\b")
STATUS = re.compile(r"^\s*(?:\*\*)?Status:(?:\*\*)?\s*(?P<status>.+?)\s*$", re.IGNORECASE)
ROW = re.compile(
    r"^\|\s*\[(?P<num>\d{3})\]\((?P<file>[^)]+)\)\s*"
    r"\|\s*(?P<title>.+?)\s*\|\s*(?P<status>.+?)\s*\|\s*$"
)
LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def normalise_status(raw: str) -> str:
    text = LINK.sub(r"\1", raw)
    text = text.split("·")[0]
    text = text.split("(")[0]
    text = re.split(r"[,.]", text)[0]
    text = re.sub(r"\bADR[- ]?(\d{1,3})\b", r"\1", text, flags=re.IGNORECASE)
    return text.strip().strip(".").strip().lower()


def adr_files() -> dict[str, Path]:
    return {
        path.name.split("-", 1)[0]: path for path in sorted(ADR_DIR.glob("[0-9][0-9][0-9]-*.md"))
    }


def heading_number(path: Path) -> tuple[str | None, str | None]:
    headings = [
        line[2:].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("# ")
    ]
    if len(headings) != 1:
        return None, None
    match = H1.match(f"# {headings[0]}")
    if match is None:
        return None, None
    return f"{int(match.group('num')):03d}", headings[0]


def adr_status(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        match = STATUS.match(line)
        if match is not None:
            return normalise_status(match.group("status"))
    return None


def index_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match is not None:
            rows.append(match.groupdict())
    return rows


def main() -> int:
    problems: list[str] = []
    files = adr_files()
    if not files:
        problems.append("docs/design/adrs: no ADR files found")

    numbers = sorted(files)
    for previous, current in itertools.pairwise(numbers):
        if int(current) != int(previous) + 1:
            problems.append(f"docs/design/adrs: numbering gap between {previous} and {current}")

    rows = index_rows()
    seen: dict[str, dict[str, str]] = {}
    for row in rows:
        num = row["num"]
        if num in seen:
            problems.append(f"docs/design/adrs/README.md: {num} listed more than once")
            continue
        seen[num] = row
        path = ADR_DIR / row["file"]
        if not path.is_file():
            problems.append(f"docs/design/adrs/README.md: {num} points at missing {row['file']}")
            continue
        if path.name.split("-", 1)[0] != num:
            problems.append(
                f"docs/design/adrs/README.md: {num} points at {row['file']} with another number"
            )
        if not row["title"].strip():
            problems.append(f"docs/design/adrs/README.md: {num} has an empty decision title")

    for num in sorted(set(files) - set(seen)):
        problems.append(
            f"docs/design/adrs/{files[num].name}: missing from docs/design/adrs/README.md"
        )
    for num in sorted(set(seen) - set(files)):
        problems.append(f"docs/design/adrs/README.md: {num} has no ADR file")

    for num, path in files.items():
        found_num, _heading = heading_number(path)
        if found_num != num:
            problems.append(
                f"docs/design/adrs/{path.name}: heading number {found_num!r} != filename {num}"
            )
        status = adr_status(path)
        if status is None:
            problems.append(f"docs/design/adrs/{path.name}: no Status line")
            continue
        row = seen.get(num)
        if row is not None and normalise_status(row["status"]) != status:
            problems.append(
                f"docs/design/adrs/README.md: {num} status {row['status']!r} != record {status!r}"
            )

    for problem in problems:
        print(problem)
    print(f"adr index: {len(files)} records, {len(rows)} rows, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
