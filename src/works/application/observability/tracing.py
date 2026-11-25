"""OpenTelemetry is always on; the exporter is opt-in.

The API is a no-op until a provider is installed, so the default daemon pays almost nothing. Setting
`WORKS_OTEL=1` installs an SDK provider: spans go to the console, or to `WORKS_OTEL_ENDPOINT` over
OTLP/HTTP. No collector is required for a local trace.
"""

from __future__ import annotations

import atexit
import contextlib
import os
from collections.abc import Iterator
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

TRACER_NAME = "works"
TRUTHY = ("1", "true", "yes", "on")

_configured = False


def enabled() -> bool:
    return os.environ.get("WORKS_OTEL", "").strip().lower() in TRUTHY


def configure_tracing() -> None:
    """Install an SDK provider once when `WORKS_OTEL` asks for real spans."""
    global _configured
    if _configured or not enabled():
        _configured = True
        return
    _configured = True
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    provider = TracerProvider()
    choice = os.environ.get("WORKS_OTEL_EXPORTER", "").strip().lower()
    endpoint = os.environ.get("WORKS_OTEL_ENDPOINT")
    exporter: Any = None
    if choice == "none":
        # Spans are created and dropped: useful for measuring instrumentation overhead.
        trace.set_tracer_provider(provider)
        atexit.register(provider.shutdown)
        return
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=endpoint)
        except ImportError:  # pragma: no cover - the server extra ships it
            exporter = None
    provider.add_span_processor(BatchSpanProcessor(exporter or ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    atexit.register(provider.shutdown)


def tracer() -> trace.Tracer:
    return trace.get_tracer(TRACER_NAME)


def current_trace_id() -> str:
    """The W3C trace id of the active span, or an empty string when tracing is off."""
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else ""


@contextlib.contextmanager
def span(name: str, **attributes: Any) -> Iterator[Span]:
    with tracer().start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value)
        try:
            yield current
        except Exception as exc:
            current.record_exception(exc)
            current.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
