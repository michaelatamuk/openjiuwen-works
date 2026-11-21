"""The live builder: openjiuwen's Claude Code harness over an Anthropic-compatible endpoint.

The harness edits the worktree directly, so the proposal carries `applied=True` and the paths it
touched. Policy is checked after the turn and before any test runs; a violation blocks the task.
This is deliberately not a patch-producing adapter: Claude Code works by editing files.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..errors import ConfigError, HarnessError
from ..gitops import GitRepo
from ..prompts import DEFAULT_PROMPT, Prompt, load_prompt
from .base import Proposal, ProposalRequest

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
    )


class LiveHarness:
    """Run one real agent turn per proposal. No fallback to a fake result."""

    name = "openjiuwen-claudecode"

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        cli_path: str | None = None,
        max_turns: int = 16,
        timeout_s: int = 600,
        prompt_path: Path | None = None,
        harness_factory: Callable[[Path], Any] | None = None,
    ) -> None:
        self._model = model or default_model()
        self._base = base_url or default_base()
        self._key = api_key or default_key()
        self._cli = cli_path if cli_path is not None else default_cli()
        self._max_turns = max_turns
        self._timeout_s = timeout_s
        self._prompt = load_prompt(prompt_path or DEFAULT_PROMPT)
        self._factory = harness_factory

    @property
    def provider(self) -> str:
        return "deepseek" if "deepseek" in self._base else "anthropic"

    def _make_harness(self, worktree: Path) -> Any:
        try:
            from openjiuwen.harness_providers.claudecode import (
                ClaudeCodeHarness,
                ClaudeCodeHarnessConfig,
                ClaudeModelConfig,
            )
        except ImportError as exc:
            raise ConfigError(
                "the live harness needs openjiuwen with the claude extra and claude-agent-sdk"
            ) from exc
        config = ClaudeCodeHarnessConfig(
            cwd=str(worktree),
            add_dirs=(str(worktree),),
            cli_path=self._cli,
            model=ClaudeModelConfig(model=self._model, api_base=self._base, api_key=self._key),
            permission_mode="bypassPermissions",
            max_turns=self._max_turns,
        )
        return ClaudeCodeHarness(config)

    async def propose(self, request: ProposalRequest) -> Proposal:
        if self._factory is not None:
            harness = self._factory(request.worktree)
        else:
            harness = self._make_harness(request.worktree)
        context, input_type, kind_type, lifecycle_type = self._protocol_types(request)
        terminal: Any = None
        trace: list[str] = []
        await harness.start(context)
        try:
            receipt = await harness.send(input_type(content=builder_prompt(request, self._prompt)))
            async with asyncio.timeout(self._timeout_s):
                async for event in harness.turn_events(receipt.turn_id):
                    payload = event.event
                    trace.append(f"{event.sequence}:{type(payload).__name__}")
                    if (
                        isinstance(payload, lifecycle_type)
                        and payload.kind is not kind_type.STARTED
                    ):
                        terminal = payload
        except TimeoutError as exc:
            raise HarnessError(
                f"the live harness did not finish within {self._timeout_s}s"
            ) from exc
        finally:
            await harness.stop()

        if terminal is None:
            raise HarnessError("the live harness produced no terminal turn event")
        if terminal.kind is not kind_type.FINISHED:
            detail = terminal.result.error if terminal.result is not None else None
            return Proposal(
                applied=True,
                trace=trace,
                prompt_name=self._prompt.name,
                prompt_sha256=self._prompt.sha256,
                model=self._model,
                provider=self.provider,
                stop=f"harness turn ended as {terminal.kind}: {detail}",
            )

        result = terminal.result
        tokens = 0
        usd = 0.0
        if result is not None and result.usage is not None:
            usage = result.usage
            tokens = usage.total_tokens or ((usage.input_tokens or 0) + (usage.output_tokens or 0))
        if result is not None and result.cost is not None:
            usd = result.cost.micros / 1_000_000
        touched = [
            path
            for path in GitRepo(request.worktree).all_changed_files(request.worktree)
            if not is_artifact(path)
        ]
        answer = ""
        if result is not None and isinstance(result.final_output, str):
            answer = result.final_output[:500]
        return Proposal(
            applied=True,
            touched_paths=touched,
            trace=trace,
            prompt_name=self._prompt.name,
            prompt_sha256=self._prompt.sha256,
            model=self._model,
            provider=self.provider,
            tokens=tokens,
            usd=usd,
            notes=[answer] if answer else [],
        )

    @staticmethod
    def _protocol_types(request: ProposalRequest) -> tuple[Any, Any, Any, Any]:
        try:
            from openjiuwen.harness_protocol import (
                HarnessContext,
                HarnessInput,
                TurnEventKind,
                TurnLifecycleEvent,
            )
        except ImportError as exc:
            raise ConfigError("the live harness needs openjiuwen.harness_protocol") from exc
        context = HarnessContext(
            agent_name="works-builder",
            agent_id="works-builder",
            host_session_id=f"works-{request.task_id}-{request.base_commit[:8]}",
            system_prompt=(
                "You are a coding agent working in one repository. Edit files directly. "
                "Never modify tests unless explicitly asked. Be concise."
            ),
            cwd=str(request.worktree),
        )
        return context, HarnessInput, TurnEventKind, TurnLifecycleEvent
