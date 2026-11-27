"""Probe the optional provider SDKs and explain how to install what is missing."""

from __future__ import annotations

import importlib.util
import os
from typing import Any


def has(module: str) -> bool:
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

# The install hints name a project extra, never a hand-copied pip list: `openjiuwen` already
# pins most of the native tree, and the extra adds the three modules it leaves out.
NATIVE_EXTRA = 'pip install "openjiuwen-works[native]"'
DSH_EXTRA = 'pip install "openjiuwen-works[dsh]"'
CODEX_EXTRA = 'pip install "openjiuwen-works[codex]"'
CLAUDE_EXTRA = 'pip install "openjiuwen-works[live]"'
EVERY_PROVIDER = 'pip install "openjiuwen-works[providers]"'


def _missing(modules: tuple[str, ...]) -> list[str]:
    return [module for module in modules if not has(module)]


def provider_setup() -> dict[str, dict[str, Any]]:
    """Return availability plus actionable setup guidance for every provider.

    The UI shows the reason and a command, instead of a bare `Needs setup`. The commands are
    suggestions, not automatic installs: Works never mutates the user's environment.
    """
    native_missing = _missing(_NATIVE_RUNTIME_MODULES)
    native_sdks = [sdk for sdk in ("anthropic", "openai") if not has(sdk)]
    native_available = (
        has("openjiuwen.harness_providers.native") and not native_missing and len(native_sdks) < 2
    )
    if has("openjiuwen.harness_providers.native") and native_missing:
        native_reason = (
            "openjiuwen is visible, but Works' Python is missing the native runtime modules: "
            + ", ".join(native_missing)
        )
        native_install = [NATIVE_EXTRA]
    elif has("openjiuwen.harness_providers.native") and len(native_sdks) == 2:
        native_reason = "Works can see openjiuwen, but no Anthropic or OpenAI SDK is installed."
        native_install = [NATIVE_EXTRA]
    elif not has("openjiuwen.harness_providers.native"):
        native_reason = (
            "openjiuwen's native DeepAgent provider is not on Works' Python path. Works uses its "
            "own Python environment, so an installation in another interpreter is not visible "
            "here. Install openjiuwen in the Works environment or run Works from its checkout."
        )
        native_install = [NATIVE_EXTRA]
    else:
        native_reason = ""
        native_install = []

    claude_missing = []
    if not has("openjiuwen.harness_providers.claudecode"):
        claude_missing.append("openjiuwen.harness_providers.claudecode")
    if not has("claude_agent_sdk"):
        claude_missing.append("claude_agent_sdk")
    claude_reason = (
        "Claude Code needs openjiuwen's claudecode provider and the Claude Agent SDK."
        if claude_missing
        else ""
    )
    claude_install = [CLAUDE_EXTRA] if claude_missing else []

    dsh_missing = not has("deepseek_harness")
    dsh_home = bool(os.environ.get("WORKS_DSH_HOME"))
    dsh_reason = ""
    dsh_install: list[str] = []
    if dsh_missing:
        dsh_reason = "The DeepSeek Harness SDK (`deepseek_harness`) is not installed."
        dsh_install.append(DSH_EXTRA)
    if not dsh_home:
        if dsh_missing:
            dsh_reason += " The DeepSeek Harness home is not set either."
        else:
            dsh_reason = (
                "The DeepSeek Harness home is not set; point Works at the DSH checkout "
                "(see docs/guides/integrations/live-harness.md)."
            )
        dsh_install.append("Set WORKS_DSH_HOME to the DeepSeek Harness home")

    codex_reason = (
        "The OpenAI Codex SDK (`openai_codex`) is not installed and no Codex CLI was found."
        if not has("openai_codex")
        else ""
    )
    codex_install = [CODEX_EXTRA] if codex_reason else []

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
                ["openjiuwen"] if not has("openjiuwen.harness_providers.native") else native_missing
            ),
        },
        "codex": {
            "available": has("openai_codex"),
            "reason": codex_reason,
            "install": codex_install,
            "missing": ["openai_codex"] if codex_reason else [],
        },
    }


def availability() -> dict[str, bool]:
    return {name: item["available"] for name, item in provider_setup().items()}
