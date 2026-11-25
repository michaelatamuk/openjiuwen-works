"""Whether the reviewer is independent enough for the risk."""

from __future__ import annotations

import os

ENV = "WORKS_REQUIRE_SPLIT_REVIEW"
HIGH = {"high", "critical"}


def required() -> bool:
    return os.environ.get(ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def independent(
    risk_level: str | None,
    *,
    provider_split: bool,
    credential_split: bool,
    refuse_self_review: bool | None = None,
) -> bool:
    """High-risk work needs a reviewer with another provider or another credential."""
    if refuse_self_review is None:
        refuse_self_review = required()
    if not refuse_self_review:
        return True
    if (risk_level or "low").lower() not in HIGH:
        return True
    return provider_split or credential_split
