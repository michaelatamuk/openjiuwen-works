"""Check that relative links inside Markdown docs point at real files.

External URLs, anchors and links inside code fences/inline code are ignored on purpose:
the docs intentionally mention files that only exist in a user's home.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("README.md", "CONTRIBUTING.md", "docs")
LINK = re.compile(r"!?\[[^\]]*\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")
SKIP_PREFIX = ("http://", "https://", "mailto:", "#", "tel:")


def markdown_files() -> list[Path]:
    files: list[Path] = []
    for name in TARGETS:
        path = ROOT / name
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.md")))
    return sorted(set(files))


def links(text: str) -> list[str]:
    stripped = FENCE.sub("", text)
    stripped = INLINE_CODE.sub("", stripped)
    return [match.group("target") for match in LINK.finditer(stripped)]


def broken(path: Path) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    text = path.read_text(encoding="utf-8")
    for target in links(text):
        if target.startswith(SKIP_PREFIX) or "://" in target:
            continue
        clean = target.split("#", 1)[0].split("?", 1)[0]
        if not clean:
            continue
        resolved = (path.parent / clean).resolve()
        if not resolved.exists():
            problems.append((path.relative_to(ROOT).as_posix(), target))
    return problems


def main() -> int:
    problems: list[tuple[str, str]] = []
    files = markdown_files()
    for path in files:
        problems.extend(broken(path))
    for source, target in problems:
        print(f"{source}: broken link -> {target}")
    print(f"checked {len(files)} markdown files, {len(problems)} broken links")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
