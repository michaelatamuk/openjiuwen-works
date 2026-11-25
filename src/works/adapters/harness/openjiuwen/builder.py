"""The live builder: openjiuwen's Claude Code harness over an Anthropic-compatible endpoint.

The harness edits the worktree directly, so the proposal carries `applied=True` and the paths it
touched. Policy is checked after the turn and before any test runs; a violation blocks the task.
This is deliberately not a patch-producing adapter: Claude Code works by editing files.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from works.adapters.git.repo import GitRepo
from works.adapters.harness.base import Proposal, ProposalRequest
from works.adapters.harness.openjiuwen.builder_defaults import (
    DEFAULT_BASE,
    DEFAULT_MODEL,
    builder_prompt,
    default_base,
    default_cli,
    default_key,
    default_model,
    is_artifact,
)
from works.adapters.harness.openjiuwen.challenge import parse_challenge
from works.adapters.harness.openjiuwen.providers import (
    create_harness,
    selected_provider,
    validate_provider,
)
from works.adapters.harness.usage import UsageTotals
from works.application.prompts import DEFAULT_PROMPT, load_prompt
from works.domain.errors import ConfigError, HarnessError
from works.domain.records import Challenge

__all__ = [
    "DEFAULT_BASE",
    "DEFAULT_MODEL",
    "LiveHarness",
    "builder_prompt",
    "default_base",
    "default_cli",
    "default_key",
    "default_model",
    "is_artifact",
]


class LiveHarness:
    """Run one real agent turn per proposal. No fallback to a fake result."""

    name = "openjiuwen"

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        verifier_model: str | None = None,
        verifier_base_url: str | None = None,
        verifier_api_key: str | None = None,
        harness_provider: str | None = None,
        verifier_harness_provider: str | None = None,
        cli_path: str | None = None,
        max_turns: int = 16,
        timeout_s: int = 600,
        prompt_path: Path | None = None,
        challenge_prompt_path: Path | None = None,
        harness_factory: Callable[[Path], Any] | None = None,
    ) -> None:
        self._model = model or default_model()
        self._base = base_url or default_base()
        self._key = api_key or default_key()
        self._verifier_model = (
            verifier_model or os.environ.get("WORKS_VERIFIER_MODEL") or self._model
        )
        self._verifier_base = (
            verifier_base_url or os.environ.get("WORKS_VERIFIER_BASE") or self._base
        )
        self._verifier_key = (
            verifier_api_key or os.environ.get("WORKS_VERIFIER_API_KEY") or self._key
        )
        self._harness_provider = validate_provider(
            harness_provider or selected_provider(), env_name="WORKS_HARNESS_PROVIDER"
        )
        self._verifier_harness_provider = validate_provider(
            verifier_harness_provider
            or os.environ.get("WORKS_VERIFIER_HARNESS_PROVIDER")
            or self._harness_provider,
            env_name="WORKS_VERIFIER_HARNESS_PROVIDER",
        )
        self._cli = cli_path if cli_path is not None else default_cli()
        self._max_turns = max_turns
        self._timeout_s = timeout_s
        self._prompt = load_prompt(prompt_path or DEFAULT_PROMPT)
        self._challenge_prompt = (
            load_prompt(challenge_prompt_path, name="challenge")
            if challenge_prompt_path is not None and challenge_prompt_path.exists()
            else None
        )
        self._factory = harness_factory

    @property
    def provider(self) -> str:
        return "deepseek" if "deepseek" in self._base else "anthropic"

    @property
    def verifier_provider(self) -> str:
        return "deepseek" if "deepseek" in self._verifier_base else "anthropic"

    @property
    def harness_provider(self) -> str:
        return self._harness_provider

    @property
    def verifier_harness_provider(self) -> str:
        return self._verifier_harness_provider

    @property
    def provider_split(self) -> bool:
        return self.verifier_provider != self.provider

    @property
    def credential_split(self) -> bool:
        return self._verifier_key != self._key

    @property
    def verifier_model(self) -> str:
        return self._verifier_model

    def _make_harness(
        self,
        worktree: Path,
        *,
        permission_mode: str = "bypassPermissions",
        verifier: bool = False,
    ) -> Any:
        provider = self._verifier_harness_provider if verifier else self._harness_provider
        model = self._verifier_model if verifier else self._model
        base = self._verifier_base if verifier else self._base
        key = self._verifier_key if verifier else self._key
        return create_harness(
            provider,
            worktree,
            model=model,
            base_url=base,
            api_key=key,
            cli_path=self._cli,
            permission_mode=permission_mode,
            max_turns=self._max_turns,
            read_only=verifier,
        )

    async def propose(self, request: ProposalRequest) -> Proposal:
        if self._factory is not None:
            harness = self._factory(request.worktree)
        else:
            harness = self._make_harness(request.worktree)
        context, input_type, kind_type, lifecycle_type = self._protocol_types(request)
        terminal: Any = None
        trace: list[str] = []
        usage_totals = UsageTotals()
        await harness.start(context)
        try:
            receipt = await harness.send(input_type(content=builder_prompt(request, self._prompt)))
            async with asyncio.timeout(self._timeout_s):
                async for event in harness.turn_events(receipt.turn_id):
                    payload = event.event
                    trace.append(f"{event.sequence}:{type(payload).__name__}")
                    usage_totals.add_event(payload)
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
                harness=self._harness_provider,
                stop=f"harness turn ended as {terminal.kind}: {detail}",
            )

        result = terminal.result
        usage_totals.add_result(result)
        tokens = usage_totals.tokens
        usd = usage_totals.usd
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
            harness=self._harness_provider,
            tokens=tokens,
            usd=usd,
            notes=[answer] if answer else [],
        )

    async def challenge(self, request: ProposalRequest, proposal: Proposal) -> Challenge:
        if self._challenge_prompt is None:
            raise ConfigError("the flow asks for a challenge but no challenge prompt is configured")
        repo = GitRepo(request.worktree)
        root = Path(tempfile.mkdtemp(prefix="works-challenge-"))
        target = root / "repo"
        harness: Any = None
        terminal: Any = None
        usage_totals = UsageTotals()
        tokens = 0
        usd = 0.0
        text = ""
        try:
            repo.worktree_add(target, request.base_commit)
            diff = repo.diff_text(request.worktree)
            if diff.strip():
                repo.apply_patch(target, diff, root / "proposal.diff")
            context, input_type, kind_type, lifecycle_type = self._protocol_types(request)
            context = replace(
                context,
                cwd=str(target),
                system_prompt=(
                    "You are an independent reviewer. Never edit files. "
                    "Return only the JSON object the user asks for."
                ),
            )
            harness = (
                self._factory(target)
                if self._factory is not None
                else self._make_harness(target, verifier=True)
            )
            await harness.start(context)
            prompt = self._challenge_prompt.render(
                worktree=str(target),
                ref=request.source_ref,
                title=request.title.strip() or request.source_ref,
            )
            receipt = await harness.send(input_type(content=prompt))
            async with asyncio.timeout(self._timeout_s):
                async for event in harness.turn_events(receipt.turn_id):
                    payload = event.event
                    usage_totals.add_event(payload)
                    if (
                        isinstance(payload, lifecycle_type)
                        and payload.kind is not kind_type.STARTED
                    ):
                        terminal = payload
        except Exception as exc:
            return Challenge(
                allow=False,
                reason=f"challenger could not run: {exc}",
                model=self._verifier_model,
                provider=self.verifier_provider,
                credential_split=self.credential_split,
                prompt_sha256=self._challenge_prompt.sha256,
            )
        finally:
            if harness is not None:
                with contextlib.suppress(Exception):
                    await harness.stop()
            with contextlib.suppress(Exception):
                repo.worktree_remove(target)
            shutil.rmtree(root, ignore_errors=True)

        if terminal is not None and terminal.result is not None:
            result = terminal.result
            usage_totals.add_result(result)
            tokens = usage_totals.tokens
            usd = usage_totals.usd
            if isinstance(result.final_output, str):
                text = result.final_output
        if terminal is None or terminal.kind is not kind_type.FINISHED:
            return Challenge(
                allow=False,
                reason="challenger did not finish",
                model=self._verifier_model,
                provider=self.verifier_provider,
                credential_split=self.credential_split,
                tokens=tokens,
                usd=usd,
                prompt_sha256=self._challenge_prompt.sha256,
            )
        return parse_challenge(
            text,
            tokens=tokens,
            usd=usd,
            model=self._verifier_model,
            provider=self.verifier_provider,
            credential_split=self.credential_split,
            prompt_sha256=self._challenge_prompt.sha256,
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
