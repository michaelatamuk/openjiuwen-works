"""Provider names and the rules for reading them from settings."""

from __future__ import annotations

import os
from typing import Literal

from works.domain.errors import ConfigError

ProviderName = Literal["claudecode", "dsh", "native", "codex"]


PROVIDER_NAMES: tuple[ProviderName, ...] = ("claudecode", "dsh", "native", "codex")


DEFAULT_PROVIDER: ProviderName = "claudecode"


def validate_provider(name: str, *, env_name: str = "WORKS_HARNESS_PROVIDER") -> ProviderName:
    raw = (name or DEFAULT_PROVIDER).strip().lower()
    if raw not in PROVIDER_NAMES:
        raise ConfigError(
            f"unknown harness provider {raw!r} from {env_name}; "
            f"expected one of {', '.join(PROVIDER_NAMES)}"
        )
    return raw


def selected_provider(env_name: str = "WORKS_HARNESS_PROVIDER") -> ProviderName:
    return validate_provider(os.environ.get(env_name) or DEFAULT_PROVIDER, env_name=env_name)


def verifier_provider() -> ProviderName:
    return selected_provider("WORKS_VERIFIER_HARNESS_PROVIDER")
