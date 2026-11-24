"""Builder harness providers exposed by openjiuwen.

Works owns the factory/selection; openjiuwen owns the protocol implementations. The old Claude
Code path stays the default. Jiuwen native is openjiuwen's in-process DeepAgent, DSH and Codex are
available when their SDKs are installed, and every optional provider fails with a configuration
error instead of a fake build when it is not.

JiuwenSwarm is deliberately not in this list: it is an external runtime selected at the builder
level, not an openjiuwen provider. See `works/harness/swarm`.
"""

from __future__ import annotations

from works.adapters.harness.openjiuwen.provider_factory import (
    _native_model_kind,
    create_harness,
)
from works.adapters.harness.openjiuwen.provider_names import (
    DEFAULT_PROVIDER,
    PROVIDER_NAMES,
    ProviderName,
    selected_provider,
    validate_provider,
    verifier_provider,
)
from works.adapters.harness.openjiuwen.provider_setup import availability, provider_setup

__all__ = [
    "DEFAULT_PROVIDER",
    "PROVIDER_NAMES",
    "ProviderName",
    "_native_model_kind",
    "availability",
    "create_harness",
    "provider_setup",
    "selected_provider",
    "validate_provider",
    "verifier_provider",
]
