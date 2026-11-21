# ADR-008 — The builder is a real openjiuwen harness, not a patch generator

**Status:** accepted · 2026-11-21

## Context

M0.5 proved the loop with a replaying fake harness. The product needs a builder that actually
reads the repository, runs commands and edits files. `openjiuwen` ships a Claude Code provider
(`openjiuwen.harness_providers.claudecode`) that speaks its protocol and drives the local
`claude` runtime. The machine has a working Anthropic-compatible endpoint
(`https://api.deepseek.com/anthropic`) and the SDK bundles a native `claude.exe`; the npm `.cmd`
launcher is refused by the SDK on Windows.

## Decision

- Add `LiveHarness` (`src/works/harness/openjiuwen.py`), selected with `works run --live`.
- One turn per proposal. The agent edits the worktree in place, so the proposal carries
  `applied=True` and the paths it touched; the supervisor does not re-apply a patch.
- Policy checks the touched paths **after the turn and before any test runs**. Bytecode and tool
  caches (`__pycache__`, `.pytest_cache`, `*.pyc`, …) are not edits and are filtered.
- The prompt fences the defect title as data, forbids test/CI/migration edits, asks for the
  smallest change and forbids commits. Raw issue bodies never reach the verifier.
- Model, provider, tokens and USD cost come from the protocol's terminal `TurnResult` and are
  recorded in `run.json` and the proof. The fake harness remains the default in CI.
- The live adapter is optional: `uv sync --extra live` installs the SDK; `openjiuwen` is supplied
  by the host installation.

## Consequences

- First live run on the fixture: 115.6 s, 104 563 tokens, $0.093938, `proved`, proof
  `74a2f1…0f19d9`.
- A live agent can edit a test before the host sees it. The worktree is disposable and the run is
  blocked, but this is detection, not prevention; the container boundary lands in M2 (ADR-004).
- Model calls are non-deterministic. CI keeps the recorded traces; live runs are manual or
  explicitly gated.
- DeepSeek is the builder provider; the verifier must use a different provider (ADR-005).

## Alternatives rejected

- **Patch-only adapter**: revert the agent's edits and turn them into a diff; loses tool calls,
  command output and the natural worktree state for no security gain.
- **Direct model HTTP**: bypasses the product harness the engine is required to use.
- **Always live**: CI would be slow, paid and flaky; recorded traces exist for a reason.
