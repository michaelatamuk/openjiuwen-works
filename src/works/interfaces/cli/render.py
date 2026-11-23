"""Plain-text rendering. No heavy imports on the CLI path."""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    cells = [[str(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in cells:
        for index, value in enumerate(row):
            if index < len(widths):
                widths[index] = max(widths[index], len(value))
    header_line = "  ".join(header.ljust(widths[i]) for i, header in enumerate(headers))
    rule = "  ".join("-" * width for width in widths)
    body = ["  ".join(value.ljust(widths[i]) for i, value in enumerate(row)) for row in cells]
    return "\n".join([header_line, rule, *body]) if body else "\n".join([header_line, rule])
