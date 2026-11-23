"""Builder harness providers exposed by openjiuwen.

Works owns the factory/selection; openjiuwen owns the protocol implementations. The old Claude
Code path stays the default. Jiuwen native is openjiuwen's in-process DeepAgent, DSH and Codex are
available when their SDKs are installed, and every optional provider fails with a configuration
error instead of a fake build when it is not.

JiuwenSwarm is deliberately not in this list: it is an external runtime selected at the builder
level, not an openjiuwen provider. See `works.harness.swarm`.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any, Literal

from ..errors import ConfigError

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


def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        return False


_NATIVE_RUNTIME_MODULES = (
    "httpx",
    "jsonschema_path",
    "aiohttp",
    "sqlalchemy",
    "tiktoken",
)


def availability() -> dict[str, bool]:
    # The native harness runs openjiuwen's in-process DeepAgent. A checkout on PYTHONPATH is not
    # enough: its core imports need the HTTP, schema and tokenizer stack. Check a few load-bearing
    # modules cheaply; a run still fails closed with the precise missing module if one slips
    # through.
    native = _has("openjiuwen.harness_providers.native") and all(
        _has(module) for module in _NATIVE_RUNTIME_MODULES
    )
    native = native and (_has("anthropic") or _has("openai"))
    return {
        "claudecode": _has("openjiuwen.harness_providers.claudecode"),
        "dsh": _has("deepseek_harness"),
        "native": native,
        "codex": _has("openai_codex"),
    }


def _native_model_kind(base_url: str) -> tuple[str, str]:
    """Map a Works endpoint onto openjiuwen's model client provider and API mode.

    The default Works endpoint is DeepSeek's Anthropic-compatible one. A bare DeepSeek/OpenAI
    endpoint uses the chat-completions dialect instead.
    """
    base = (base_url or "").lower()
    if "anthropic" in base:
        return "Anthropic", "anthropic_messages"
    if "deepseek" in base:
        return "DeepSeek", "chat_completions"
    return "OpenAI", "chat_completions"


def _native_harness(
    worktree: Path,
    *,
    model: str,
    base_url: str,
    api_key: str,
    max_turns: int,
    read_only: bool,
) -> Any:
    """Build openjiuwen's in-process DeepAgent harness from a minimal DeepAgentSpec.

    The spec is the smallest one that is a real coding agent: a model, the worktree as the
    workspace/sandbox, and the system-operation rail that registers file and shell tools. A
    verifier gets the same rail read-only, so it can inspect but not edit.
    """
    from openjiuwen.core.foundation.llm import (
        LLMApiMode,
        ModelClientConfig,
        ModelRequestConfig,
    )
    from openjiuwen.core.single_agent.schema.agent_card import AgentCard
    from openjiuwen.harness.schema.deep_agent_spec import (
        DeepAgentSpec,
        RailSpec,
        TeamModelConfig,
        WorkspaceSpec,
    )
    from openjiuwen.harness_providers.factory import resolve_provider

    client_provider, api_mode = _native_model_kind(base_url)
    sdk = "anthropic" if client_provider == "Anthropic" else "openai"
    if not _has(sdk):
        raise ConfigError(
            f"the native harness needs the `{sdk}` SDK for {client_provider} endpoints"
        )

    spec = DeepAgentSpec(
        card=AgentCard(
            id="works-builder",
            name="works-builder",
            description="Works builder: one real agent turn over the task worktree",
        ),
        model=TeamModelConfig(
            model_client_config=ModelClientConfig(
                client_provider=client_provider,
                api_key=api_key,
                api_base=base_url,
                api_mode=LLMApiMode(api_mode),
            ),
            model_request_config=ModelRequestConfig(model=model),
        ),
        system_prompt=(
            "You are a coding agent working in one repository. Edit files directly. "
            "Never modify tests unless explicitly asked. Be concise."
        ),
        workspace=WorkspaceSpec(root_path=str(worktree), language="en"),
        cwd=str(worktree),
        project_root=str(worktree),
        rails=[RailSpec(type="core.sys_operation", params={"read_only": read_only})],
        max_iterations=max_turns,
        enable_task_loop=False,
        auto_create_workspace=False,
        restrict_to_sandbox=True,
        language="en",
    )
    provider = resolve_provider("native")
    return provider.create({"deep_agent": spec.model_dump(mode="json")})


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
    read_only: bool = False,
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

    if provider == "native":
        if not availability()["native"]:
            raise ConfigError(
                "the native Jiuwen harness needs openjiuwen's in-process DeepAgent runtime "
                "(`openjiuwen.harness_providers.native`, `httpx` and the endpoint SDK)"
            )
        return _native_harness(
            worktree,
            model=model,
            base_url=base_url,
            api_key=api_key,
            max_turns=max_turns,
            read_only=read_only,
        )

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
