"""Read-only harness planner and critic.

Both roles use the same boundary: one read-only agent turn over the repository, one JSON result,
no edits and no self-approval. `works.planner` merges and lints the proposal; the supervisor still
owns the human gate.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import ConfigError
from ..planner import (
    PlanCritique,
    PlannerContext,
    PlannerOutput,
    PlanProposal,
    PlanProvenance,
    PlanVersion,
    context_payload,
    deterministic_proposal,
)
from ..prompts import Prompt, load_prompt
from .providers import ProviderName, create_harness, validate_provider
from .usage import UsageTotals

_PLAN_PROVIDERS = frozenset({"claudecode", "native"})
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class TurnOutput:
    text: str
    tokens: int = 0
    usd: float = 0.0


def _final_text(result: Any) -> str:
    if result is not None and isinstance(result.final_output, str):
        return result.final_output
    parts: list[str] = []
    if result is not None:
        for message in getattr(result, "messages", ()) or ():
            for block in getattr(message, "content", ()) or ():
                content = getattr(block, "content", None)
                if isinstance(content, str):
                    parts.append(content)
    return "\n".join(parts)


def _json_object(text: str, what: str) -> dict[str, Any]:
    match = _JSON_OBJECT.search(text)
    if match is None:
        raise ConfigError(f"the {what} returned no JSON object")
    try:
        payload: Any = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"the {what} returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"the {what} returned a non-object JSON value")
    return payload


def parse_plan_json(text: str) -> PlanProposal:
    try:
        return PlanProposal.model_validate(_json_object(text, "planner"))
    except ValueError as exc:
        raise ConfigError(f"the planner proposal is invalid: {exc}") from exc


def parse_critique_json(text: str) -> PlanCritique:
    try:
        return PlanCritique.model_validate(_json_object(text, "critic"))
    except ValueError as exc:
        raise ConfigError(f"the critic verdict is invalid: {exc}") from exc


def _validate_plan_provider(provider: str) -> ProviderName:
    selected = validate_provider(provider, env_name="planner provider")
    if selected not in _PLAN_PROVIDERS:
        raise ConfigError(
            f"the planner does not support {selected!r} yet; use claudecode or native"
        )
    return selected


async def _run_turn(
    *,
    provider: ProviderName,
    model: str,
    base_url: str,
    api_key: str,
    cwd: Path,
    session_id: str,
    system_prompt: str,
    prompt: str,
    cli_path: str | None,
    max_turns: int,
    timeout_s: int,
) -> TurnOutput:
    try:
        from openjiuwen.harness_protocol import (
            HarnessContext,
            HarnessInput,
            TurnEventKind,
            TurnLifecycleEvent,
        )
    except ImportError as exc:
        raise ConfigError("the planner needs openjiuwen.harness_protocol") from exc

    harness = create_harness(
        provider,
        cwd,
        model=model,
        base_url=base_url,
        api_key=api_key,
        cli_path=cli_path,
        permission_mode="plan",
        max_turns=max_turns,
        read_only=True,
    )
    harness_context = HarnessContext(
        agent_name="works-planner",
        agent_id="works-planner",
        host_session_id=session_id,
        system_prompt=system_prompt,
        cwd=str(cwd),
    )
    terminal: Any = None
    usage_totals = UsageTotals()
    await harness.start(harness_context)
    try:
        receipt = await harness.send(HarnessInput(content=prompt))
        async with asyncio.timeout(timeout_s):
            async for event in harness.turn_events(receipt.turn_id):
                payload = event.event
                usage_totals.add_event(payload)
                if (
                    isinstance(payload, TurnLifecycleEvent)
                    and payload.kind is not TurnEventKind.STARTED
                ):
                    terminal = payload
    except TimeoutError as exc:
        raise ConfigError(f"the planner turn did not finish within {timeout_s}s") from exc
    finally:
        with contextlib.suppress(Exception):
            await harness.stop()

    if terminal is None:
        raise ConfigError("the planner turn produced no terminal event")
    if terminal.kind is not TurnEventKind.FINISHED:
        detail = terminal.result.error if terminal.result is not None else None
        raise ConfigError(f"the planner turn ended as {terminal.kind}: {detail}")
    usage_totals.add_result(terminal.result)
    return TurnOutput(
        text=_final_text(terminal.result),
        tokens=usage_totals.tokens,
        usd=usage_totals.usd,
    )


class HarnessPlanner:
    """Draft a plan with a read-only OpenJiuwen harness."""

    name: str

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str,
        prompt_path: Path,
        cli_path: str | None = None,
        max_turns: int = 8,
        timeout_s: int = 300,
    ) -> None:
        self._provider: ProviderName = _validate_plan_provider(provider)
        self._model = model
        self._base = base_url
        self._key = api_key
        self._prompt_path = prompt_path
        self._cli = cli_path
        self._max_turns = max_turns
        self._timeout_s = timeout_s
        self.name = self._provider

    def _prompt(self, context: PlannerContext, feedback: str = "") -> Prompt:
        prompt = load_prompt(self._prompt_path, name="plan")
        deterministic = deterministic_proposal(context).model_dump_json(indent=2)
        payload = json.dumps(context_payload(context), indent=2, ensure_ascii=False)
        return Prompt(
            name=prompt.name,
            path=prompt.path,
            text=prompt.render(
                worktree=str(context.repo),
                ref=context.source_ref,
                title=context.source_title,
                flow=context.flow.flow,
                context=payload,
                deterministic=deterministic,
                feedback=feedback,
            ),
            sha256=prompt.sha256,
        )

    async def draft(self, context: PlannerContext) -> PlannerOutput:
        return await self._draft(context, "")

    async def draft_with_feedback(
        self,
        context: PlannerContext,
        previous: PlanProposal,
        errors: list[str],
    ) -> PlannerOutput:
        feedback = (
            "The previous plan failed the deterministic lint. Correct these errors and return a "
            "complete replacement JSON object.\n"
            + "\n".join(f"- {error}" for error in errors)
            + f"\n\nPrevious summary: {previous.summary}\n"
        )
        return await self._draft(context, feedback)

    async def _draft(self, context: PlannerContext, feedback: str) -> PlannerOutput:
        prompt = self._prompt(context, feedback)
        started = time.monotonic()
        turn = await _run_turn(
            provider=self._provider,
            model=self._model,
            base_url=self._base,
            api_key=self._key,
            cwd=context.repo,
            session_id=f"works-plan-{context.task_id}-{context.base_commit[:8]}",
            system_prompt=(
                "You are a planning agent. Read the repository. Never edit files. "
                "Return only one JSON object matching the requested schema."
            ),
            prompt=prompt.text,
            cli_path=self._cli,
            max_turns=self._max_turns,
            timeout_s=self._timeout_s,
        )
        try:
            proposal = parse_plan_json(turn.text)
        except ConfigError as exc:
            raise ConfigError(f"{exc}; planner output began: {turn.text[:400]!r}") from exc
        if turn.tokens == 0:
            proposal = proposal.model_copy(
                update={
                    "notes": [
                        *proposal.notes,
                        f"The {self._provider} harness did not expose token usage for this "
                        "planning turn; planner cost is recorded conservatively as zero.",
                    ]
                }
            )
        return PlannerOutput(
            proposal=proposal,
            provenance=PlanProvenance(
                planner=self.name,
                provider=self._provider,
                model=self._model,
                prompt_sha256=prompt.sha256,
                tokens=turn.tokens,
                usd=turn.usd,
                duration_ms=int((time.monotonic() - started) * 1000),
            ),
        )


class HarnessCritic:
    """An independent read-only critic for deep plan mode."""

    name: str

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str,
        prompt_path: Path,
        cli_path: str | None = None,
        max_turns: int = 6,
        timeout_s: int = 240,
    ) -> None:
        self._provider: ProviderName = _validate_plan_provider(provider)
        self._model = model
        self._base = base_url
        self._key = api_key
        self._prompt_path = prompt_path
        self._cli = cli_path
        self._max_turns = max_turns
        self._timeout_s = timeout_s
        self.name = self._provider

    def _prompt(self, context: PlannerContext, plan: PlanVersion) -> Prompt:
        prompt = load_prompt(self._prompt_path, name="plan-critique")
        payload = json.dumps(context_payload(context), indent=2, ensure_ascii=False)
        plan_payload = plan.model_dump_json(indent=2)
        return Prompt(
            name=prompt.name,
            path=prompt.path,
            text=prompt.render(
                worktree=str(context.repo),
                ref=context.source_ref,
                title=context.source_title,
                flow=context.flow.flow,
                context=payload,
                plan=plan_payload,
            ),
            sha256=prompt.sha256,
        )

    async def review(self, context: PlannerContext, plan: PlanVersion) -> PlanCritique:
        prompt = self._prompt(context, plan)
        try:
            turn = await _run_turn(
                provider=self._provider,
                model=self._model,
                base_url=self._base,
                api_key=self._key,
                cwd=context.repo,
                session_id=f"works-plan-critic-{context.task_id}-{plan.hash[:8]}",
                system_prompt=(
                    "You are an independent plan critic. Read the repository. Never edit files. "
                    "Return only one JSON object matching the requested schema."
                ),
                prompt=prompt.text,
                cli_path=self._cli,
                max_turns=self._max_turns,
                timeout_s=self._timeout_s,
            )
            verdict = parse_critique_json(turn.text)
        except ConfigError as exc:
            return PlanCritique(
                allow=False,
                score=0.0,
                concerns=[f"the critic could not run: {exc}"],
                model=self._model,
                provider=self._provider,
                prompt_sha256=prompt.sha256,
            )
        return verdict.model_copy(
            update={
                "model": verdict.model or self._model,
                "provider": verdict.provider or self._provider,
                "prompt_sha256": prompt.sha256,
                "tokens": turn.tokens,
                "usd": turn.usd,
            }
        )
