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
    "sqlmodel",
    "tiktoken",
    "oauthlib",
    "openai",
    "pymilvus",
    "tqdm",
    "dashscope",
    "pdfplumber",
    "trafilatura",
    "transformers",
    "alembic",
)

_MODULE_PACKAGES = {
    "httpx": "httpx>=0.24",
    "jsonschema_path": "jsonschema-path",
    "aiohttp": "aiohttp>=3.14.4",
    "sqlalchemy": "sqlalchemy[asyncio]>=2.0.41",
    "sqlmodel": "sqlmodel>=0.0.37",
    "tiktoken": "tiktoken>=0.12.0",
    "oauthlib": "oauthlib>=4.0.0",
    "openai": "openai>=1.108.0",
    "pymilvus": "pymilvus>=2.6.2,<2.6.10",
    "tqdm": "tqdm",
    "dashscope": "dashscope>=1.25.6",
    "pdfplumber": "pdfplumber>=0.11.8",
    "trafilatura": "trafilatura>=1.6.0",
    "transformers": "transformers>=4.52.4",
    "alembic": "alembic>=1.13.1",
}


def _missing(modules: tuple[str, ...]) -> list[str]:
    return [module for module in modules if not _has(module)]


def _install(packages: list[str]) -> list[str]:
    if not packages:
        return []
    return [f"pip install {' '.join(packages)}"]


def provider_setup() -> dict[str, dict[str, Any]]:
    """Return availability plus actionable setup guidance for every provider.

    The UI shows the reason and a command, instead of a bare `Needs setup`. The commands are
    suggestions, not automatic installs: Works never mutates the user's environment.
    """
    native_missing = _missing(_NATIVE_RUNTIME_MODULES)
    native_sdks = [sdk for sdk in ("anthropic", "openai") if not _has(sdk)]
    native_available = (
        _has("openjiuwen.harness_providers.native") and not native_missing and len(native_sdks) < 2
    )
    if _has("openjiuwen.harness_providers.native") and native_missing:
        native_reason = (
            "openjiuwen is visible, but Works' Python is missing the native runtime modules: "
            + ", ".join(native_missing)
        )
        native_install = _install([_MODULE_PACKAGES[module] for module in native_missing])
    elif _has("openjiuwen.harness_providers.native") and len(native_sdks) == 2:
        native_reason = "Works can see openjiuwen, but no Anthropic or OpenAI SDK is installed."
        native_install = _install(["anthropic", "openai"])
    elif not _has("openjiuwen.harness_providers.native"):
        native_reason = (
            "openjiuwen's native DeepAgent provider is not on Works' Python path. Works uses its "
            "own Python environment, so an installation in another interpreter is not visible "
            "here. Install openjiuwen in the Works environment or run Works from its checkout."
        )
        native_install = ["pip install openjiuwen"]
    else:
        native_reason = ""
        native_install = []

    claude_missing = []
    if not _has("openjiuwen.harness_providers.claudecode"):
        claude_missing.append("openjiuwen.harness_providers.claudecode")
    if not _has("claude_agent_sdk"):
        claude_missing.append("claude_agent_sdk")
    claude_reason = (
        "Claude Code needs openjiuwen's claudecode provider and the Claude Agent SDK."
        if claude_missing
        else ""
    )
    claude_install = ["uv sync --extra live"] if claude_missing else []

    dsh_missing = not _has("deepseek_harness")
    dsh_home = bool(os.environ.get("WORKS_DSH_HOME"))
    dsh_reason = ""
    dsh_install: list[str] = []
    if dsh_missing:
        dsh_reason = "The DeepSeek Harness SDK (`deepseek_harness`) is not installed."
        dsh_install.append("pip install deepseek-harness-sdk")
    elif not dsh_home:
        dsh_reason = (
            "The DeepSeek Harness home is not set; point Works at the DSH checkout "
            "(see docs/live-harness.md)."
        )
        dsh_install.append("Set the DeepSeek Harness home in your shell")

    codex_reason = (
        "The OpenAI Codex SDK (`openai_codex`) is not installed and no Codex CLI was found."
        if not _has("openai_codex")
        else ""
    )
    codex_install = ["pip install openai-codex"] if codex_reason else []

    return {
        "claudecode": {
            "available": not claude_missing,
            "reason": claude_reason,
            "install": claude_install,
            "missing": claude_missing,
        },
        "dsh": {
            "available": not dsh_missing and dsh_home,
            "reason": dsh_reason,
            "install": dsh_install,
            "missing": ["deepseek_harness"] if dsh_missing else [],
        },
        "native": {
            "available": native_available,
            "reason": native_reason,
            "install": native_install,
            "missing": (
                ["openjiuwen"]
                if not _has("openjiuwen.harness_providers.native")
                else native_missing
            ),
        },
        "codex": {
            "available": _has("openai_codex"),
            "reason": codex_reason,
            "install": codex_install,
            "missing": ["openai_codex"] if codex_reason else [],
        },
    }


def availability() -> dict[str, bool]:
    return {name: item["available"] for name, item in provider_setup().items()}


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
