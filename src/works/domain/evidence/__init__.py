"""Evidence is computed, not narrated. A proof page is a pure function of one run."""

from __future__ import annotations

from works.domain.evidence.models import (
    MAX_DIFF_CHARS,
    Artifact,
    DiffStatRow,
    Evidence,
    priority_order,
    violations_report,
)
from works.domain.evidence.render import render_markdown
from works.domain.evidence.store import write_evidence
from works.domain.evidence.summary import render_summary, summary_digest

__all__ = [
    "MAX_DIFF_CHARS",
    "Artifact",
    "DiffStatRow",
    "Evidence",
    "priority_order",
    "render_markdown",
    "render_summary",
    "summary_digest",
    "violations_report",
    "write_evidence",
]
