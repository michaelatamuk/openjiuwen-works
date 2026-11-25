"""Tracing is a no-op by default and a real console trace when `WORKS_OTEL=1`."""

from __future__ import annotations

import os
import subprocess
import sys

from works.application.observability import tracing


def test_tracing_is_a_no_op_by_default(monkeypatch) -> None:
    monkeypatch.delenv("WORKS_OTEL", raising=False)
    monkeypatch.setattr(tracing, "_configured", False)

    tracing.configure_tracing()

    assert tracing.enabled() is False
    assert tracing.current_trace_id() == ""
    with tracing.span("works.test", answer=42) as current:
        assert current is not None


TRACE_SCRIPT = """
import os

os.environ["WORKS_OTEL"] = "1"

from opentelemetry import trace

from works.application.observability.tracing import configure_tracing, span

configure_tracing()
with span("works.test", answer=42):
    pass
provider = trace.get_tracer_provider()
provider.force_flush()
provider.shutdown()
"""


def test_enabling_otel_exports_a_finished_span() -> None:
    result = subprocess.run(
        [sys.executable, "-c", TRACE_SCRIPT],
        env={**os.environ, "WORKS_OTEL": "1"},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "works.test" in result.stdout
    assert "answer" in result.stdout
