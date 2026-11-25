"""Parse the challenger turn into a typed challenge verdict."""

from __future__ import annotations

import json
import re

from works.domain.records import Challenge


def parse_challenge(
    text: str,
    *,
    tokens: int,
    usd: float,
    model: str,
    provider: str,
    version: str = "unknown",
    credential_split: bool,
    prompt_sha256: str,
) -> Challenge:
    match = re.search(r"\{.*\}", text, re.S)
    try:
        payload = json.loads(match.group(0)) if match else {}
        allow = payload.get("allow")
        if not isinstance(allow, bool):
            raise ValueError("allow is not a boolean")
        concerns = payload.get("concerns", [])
        if not isinstance(concerns, list):
            concerns = []
        return Challenge(
            allow=allow,
            reason=str(payload.get("reason") or ""),
            concerns=[str(item) for item in concerns],
            model=model,
            provider=provider,
            version=version,
            credential_split=credential_split,
            tokens=tokens,
            usd=usd,
            prompt_sha256=prompt_sha256,
        )
    except (ValueError, json.JSONDecodeError):
        return Challenge(
            allow=False,
            reason="challenger did not return a valid JSON verdict",
            concerns=[text[:300]] if text else [],
            model=model,
            provider=provider,
            version=version,
            credential_split=credential_split,
            tokens=tokens,
            usd=usd,
            prompt_sha256=prompt_sha256,
        )
