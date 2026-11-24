"""Readiness: may this repository be automated at all?

The gate is deliberately boring: it runs the commands the repository declares in
`.works/readiness.yaml`, finds unapproved suppressions and requires a feature map. A red gate is a
refusal, not a warning; the caller decides whether to block an autonomous run.
"""

from __future__ import annotations

from works.application.execution.readiness.gate import assess, ensure_ready
from works.application.execution.readiness.scan import (
    find_suppressions,
    import_graph,
    import_violations,
)
from works.application.execution.readiness.spec import (
    COMMANDS,
    SPEC_PATH,
    Boundaries,
    BoundaryRule,
    CheckResult,
    CheckStatus,
    Commands,
    ReadinessReport,
    ReadinessSpec,
    ReportStatus,
    SuppressionFinding,
    Suppressions,
    load_spec,
)

__all__ = [
    "COMMANDS",
    "SPEC_PATH",
    "Boundaries",
    "BoundaryRule",
    "CheckResult",
    "CheckStatus",
    "Commands",
    "ReadinessReport",
    "ReadinessSpec",
    "ReportStatus",
    "SuppressionFinding",
    "Suppressions",
    "assess",
    "ensure_ready",
    "find_suppressions",
    "import_graph",
    "import_violations",
    "load_spec",
]
