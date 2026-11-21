"""R7 capability spike: drive the real local Claude Code CLI through openjiuwen's harness.

This is not a Works test. It answers one question: can the local agent runtime edit a small
repository, with the model reached through the environment's Anthropic-compatible endpoint?
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from openjiuwen.harness_protocol import HarnessContext, HarnessInput, TurnEventKind
from openjiuwen.harness_providers.claudecode import (
    ClaudeCodeHarness,
    ClaudeCodeHarnessConfig,
    ClaudeModelConfig,
)

ROOT = Path(__file__).resolve().parents[1]


def prepare(workdir: Path | None) -> Path:
    if workdir is not None:
        return workdir.expanduser().resolve()
    target = Path(tempfile.mkdtemp(prefix="works-spike-")) / "repo"
    shutil.copytree(ROOT / "fixtures" / "fixture-repo", target)
    return target


async def run(workdir: Path, prompt: str) -> int:
    cli = os.environ.get("CLAUDE_CLI")
    if cli is not None and not Path(cli).is_file():
        print(f"CLAUDE_CLI does not exist: {cli}")
        return 2
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY is not set")
        return 2
    model = os.environ.get("WORKS_MODEL", "deepseek-chat")
    base = os.environ.get("WORKS_MODEL_BASE", "https://api.deepseek.com/anthropic")
    config = ClaudeCodeHarnessConfig(
        cwd=str(workdir),
        add_dirs=(str(workdir),),
        cli_path=cli,
        model=ClaudeModelConfig(model=model, api_base=base, api_key=api_key),
        permission_mode="bypassPermissions",
        max_turns=16,
    )
    harness = ClaudeCodeHarness(config)
    context = HarnessContext(
        agent_name="works-builder",
        agent_id="works-builder",
        host_session_id=f"works-spike-{os.getpid()}",
        system_prompt=(
            "You are a coding agent working in one repository. Edit files directly. "
            "Do not modify tests unless explicitly asked. Be concise."
        ),
        cwd=str(workdir),
    )
    await harness.start(context)
    try:
        receipt = await harness.send(HarnessInput(content=prompt))
        kinds: list[str] = []
        terminal = None
        async for event in harness.turn_events(receipt.turn_id):
            payload = event.event
            if hasattr(payload, "kind"):
                kind = str(payload.kind)
                kinds.append(kind)
                if kind in {"TurnEventKind.FINISHED", "TurnEventKind.FAILED", "TurnEventKind.ABORTED"}:
                    terminal = payload
        print("events:", ", ".join(kinds[-12:]))
        print("terminal:", terminal.kind if terminal else "none")
        if terminal is not None and terminal.result is not None:
            print("answer:", str(terminal.result.final_output)[:2000])
            if terminal.result.error is not None:
                print("error:", terminal.result.error)
        source = (workdir / "calc" / "core.py").read_text(encoding="utf-8")
        print("--- calc/core.py ---")
        print(source)
        return 0 if terminal is not None and terminal.kind is TurnEventKind.FINISHED else 1
    finally:
        await harness.stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", type=Path, default=None)
    parser.add_argument(
        "--prompt",
        default=(
            "The test tests/test_core.py fails because add() in calc/core.py subtracts. "
            "Fix add() so it returns the sum, and do not modify tests. Reply DONE when the test passes."
        ),
    )
    args = parser.parse_args()
    workdir = prepare(args.workdir)
    print("workdir:", workdir)
    return asyncio.run(run(workdir, args.prompt))


if __name__ == "__main__":
    raise SystemExit(main())
