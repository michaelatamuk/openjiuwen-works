"""Defaults and the builder prompt for the live openjiuwen harness."""

from __future__ import annotations

import os
from pathlib import Path

from works.adapters.harness.base import ProposalRequest
from works.application.prompts import DEFAULT_PROMPT, Prompt, load_prompt
from works.domain.errors import ConfigError

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE = "https://api.deepseek.com/anthropic"
_ARTIFACT_PARTS = frozenset(
    {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis"}
)


def is_artifact(path: str) -> bool:
    """Bytecode and tool caches are by-products, not edits, and are never policy-relevant."""
    parts = set(Path(path).parts)
    return bool(parts & _ARTIFACT_PARTS) or path.endswith((".pyc", ".pyo"))


def default_model() -> str:
    return os.environ.get("WORKS_MODEL", DEFAULT_MODEL)


def default_base() -> str:
    return os.environ.get("WORKS_MODEL_BASE", DEFAULT_BASE)


def default_key() -> str:
    key = os.environ.get("WORKS_MODEL_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ConfigError(
            "no model key: set ANTHROPIC_API_KEY (or WORKS_MODEL_KEY) for the live harness"
        )
    return key


def default_cli() -> str | None:
    cli = os.environ.get("CLAUDE_CLI")
    if cli is None:
        return None
    if cli.lower().endswith((".cmd", ".bat")):
        raise ConfigError(
            "CLAUDE_CLI points at a batch file; the Claude Agent SDK refuses .cmd/.bat on Windows. "
            "Use the bundled claude.exe or install the native build."
        )
    return cli


def builder_prompt(request: ProposalRequest, prompt: Prompt | None = None) -> str:
    loaded = prompt or load_prompt(DEFAULT_PROMPT)
    return loaded.render(
        worktree=str(request.worktree),
        ref=request.source_ref,
        title=request.title.strip() or request.source_ref,
        plan=str(request.plan.get("brief") or "No plan brief was recorded."),
    )
