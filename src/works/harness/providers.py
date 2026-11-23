"""Builder harness providers exposed by openjiuwen.

Works owns the factory/selection; openjiuwen owns the protocol implementations. The old Claude
Code path stays the default. DSH and Codex are available when their SDKs are installed, and fail
with a configuration error instead of a fake build when they are not.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any, Literal

from ..errors import ConfigError

ProviderName = Literal["claudecode", "dsh", "codex"]
PROVIDER_NAMES: tuple[ProviderName, ...] = ("claudecode", "dsh", "codex")
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


def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        return False


def availability() -> dict[str, bool]:
    return {
        "claudecode": _has("openjiuwen.harness_providers.claudecode"),
        "dsh": _has("deepseek_harness"),
        "codex": _has("openai_codex"),
    }


def create_harness(
    provider: ProviderName,
    worktree: Path,
    *,
    model: str,
    base_url: str,
    api_key: str,
    cli_path: str | None = None,
    permission_mode: str = "bypassPermissions",
    max_turns: int = 16,
    env: dict[str, str] | None = None,
) -> Any:
    """Build an unstarted harness implementing `openjiuwen.harness_protocol`."""
    if provider == "claudecode":
        from openjiuwen.harness_providers.claudecode import (
            ClaudeCodeHarness,
            ClaudeCodeHarnessConfig,
            ClaudeModelConfig,
        )

        config = ClaudeCodeHarnessConfig(
            cwd=str(worktree),
            add_dirs=(str(worktree),),
            cli_path=cli_path,
            model=ClaudeModelConfig(model=model, api_base=base_url, api_key=api_key),
            permission_mode=permission_mode,
            max_turns=max_turns,
        )
        return ClaudeCodeHarness(config)

    if provider == "dsh":
        if not availability()["dsh"]:
            raise ConfigError(
                "the dsh harness needs the DeepSeek Harness SDK "
                "(`deepseek_harness`) and WORKS_DSH_HOME"
            )
        from openjiuwen.harness_providers.dsh import DshHarness, DshHarnessConfig

        home = os.environ.get("WORKS_DSH_HOME")
        if not home:
            raise ConfigError("the dsh harness needs WORKS_DSH_HOME (never falls back to ~/.dsh)")
        config = DshHarnessConfig(
            provider=os.environ.get("WORKS_DSH_PROVIDER") or "deepseek-official",
            model=model,
            base_url=base_url,
            api_key=api_key,
            cwd=str(worktree),
            dsh_home=home,
            env=env or {},
        )
        return DshHarness(config)

    if provider == "codex":
        if not availability()["codex"]:
            raise ConfigError(
                "the codex harness needs the OpenAI Codex SDK (`openai_codex`) or a Codex CLI"
            )
        from openjiuwen.harness_providers.codex import (
            CodexHarness,
            CodexHarnessConfig,
            CodexModelConfig,
        )

        config = CodexHarnessConfig(
            cwd=str(worktree),
            model=CodexModelConfig(
                model=model,
                provider=os.environ.get("WORKS_CODEX_PROVIDER") or "deepseek",
                api_base=base_url,
                api_key=api_key,
            ),
            env=env or {},
        )
        return CodexHarness(config)

    raise ConfigError(f"unsupported harness provider {provider!r}")
