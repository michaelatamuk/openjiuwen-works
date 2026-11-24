"""One read-only harness turn, with its usage totals."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from works.adapters.harness.openjiuwen.providers import ProviderName, create_harness
from works.adapters.harness.usage import UsageTotals
from works.domain.errors import ConfigError


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
