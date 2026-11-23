"""Extract token usage from harness provider events.

The native harness exposes usage on a provider event (`usage_metadata`) rather than on
`TurnResult.usage`. Claude Code and some providers put it on the result. Works sums whatever the
stream carries so cost evidence is not tied to one harness implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


@dataclass
class UsageTotals:
    tokens: int = 0
    usd: float = 0.0
    calls: int = 0

    def add_event(self, payload: Any) -> None:
        data = _mapping(getattr(payload, "payload", None))
        if data is None:
            data = _mapping(getattr(payload, "data", None))
        if data is None:
            return
        usage = _mapping(data.get("usage_metadata")) or _mapping(data.get("usage"))
        if usage is None:
            return
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        total = int(usage.get("total_tokens") or (input_tokens + output_tokens))
        if total <= 0:
            return
        self.tokens += total
        cost = usage.get("total_cost")
        if cost is None:
            cost = float(usage.get("input_cost") or 0.0) + float(usage.get("output_cost") or 0.0)
        self.usd += float(cost or 0.0)
        self.calls += 1

    def add_result(self, result: Any) -> None:
        usage = getattr(result, "usage", None)
        if usage is not None:
            tokens = int(
                getattr(usage, "total_tokens", 0)
                or (
                    int(getattr(usage, "input_tokens", 0) or 0)
                    + int(getattr(usage, "output_tokens", 0) or 0)
                )
            )
            if tokens > self.tokens:
                self.tokens = tokens
        cost = getattr(result, "cost", None)
        if cost is not None:
            usd = float(getattr(cost, "micros", 0) or 0) / 1_000_000
            if usd > self.usd:
                self.usd = usd
