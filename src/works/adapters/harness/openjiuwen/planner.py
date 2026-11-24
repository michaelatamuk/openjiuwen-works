"""Read-only harness planner and critic.

Both roles use the same boundary: one read-only agent turn over the repository, one JSON result,
no edits and no self-approval. `works.planner` merges and lints the proposal; the supervisor still
owns the human gate.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from works.adapters.harness.openjiuwen.planner_parsing import (
    _validate_plan_provider,
    parse_critique_json,
    parse_plan_json,
)
from works.adapters.harness.openjiuwen.planner_turn import _run_turn
from works.adapters.harness.openjiuwen.providers import ProviderName
from works.application.planning.service import (
    PlanCritique,
    PlannerContext,
    PlannerOutput,
    PlanProposal,
    PlanProvenance,
    PlanVersion,
    context_payload,
    deterministic_proposal,
)
from works.application.prompts import Prompt, load_prompt
from works.domain.errors import ConfigError

__all__ = ["HarnessCritic", "HarnessPlanner", "parse_critique_json", "parse_plan_json"]


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
