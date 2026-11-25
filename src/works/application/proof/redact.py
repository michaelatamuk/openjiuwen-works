"""Remove credentials from proof-visible text before it is written."""

from __future__ import annotations

import re

PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"gho_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*[\"\']?[A-Za-z0-9_\-]{16,}"),
)
PLACEHOLDER = "[redacted]"


def redact(text: str) -> tuple[str, int]:
    count = 0
    for pattern in PATTERNS:
        text, hits = pattern.subn(PLACEHOLDER, text)
        count += hits
    return text, count
