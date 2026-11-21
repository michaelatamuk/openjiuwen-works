# Live harness

`works run --live` uses the real builder: `openjiuwen`'s Claude Code harness, the native
`claude.exe` bundled with `claude-agent-sdk`, and an Anthropic-compatible model endpoint.

## Setup

```bash
uv sync --extra live
# openjiuwen must be installed, or on PYTHONPATH (the agent-core checkout is enough)
```

Environment:

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | model key; `WORKS_MODEL_KEY` also works |
| `WORKS_MODEL` | `deepseek-chat` | model id recorded per run |
| `WORKS_MODEL_BASE` | `https://api.deepseek.com/anthropic` | Anthropic-compatible endpoint |
| `CLAUDE_CLI` | SDK-bundled `claude.exe` | must be an `.exe`; `.cmd`/`.bat` are refused |

`ANTHROPIC_BASE_URL` in the shell may point elsewhere; the harness injects the explicit
`--model-base` through the CLI settings layer, so the run is reproducible.

## Run

```bash
works run <task> --live --approve-plan --scenarios fixtures/scenarios/fix-add.yaml
```

The agent edits the worktree directly. The supervisor:

1. checks every touched path against policy, ignoring bytecode/tool caches;
2. blocks on a test, migration, workflow or scenario edit;
3. runs the repository tests and the P0/P1 scenarios;
4. computes the proof and records model, provider, tokens, USD and the prompt hash.

## Prompts

The builder prompt is a versioned file: `flows/fix-issue/prompts/build.md`. It is rendered with
safe substitution for `$worktree`, `$ref` and `$title`; the defect title is fenced as data. The
SHA-256 of the prompt is written to `harness.json` and the proof, so a prompt change is visible in
review and cannot hide behind a model change.

## Measured on the development host

| Run | Time | Tokens | USD | Result |
|---|---|---|---|---|
| `LIVE-2` on the fixture | 115.6 s | 104 563 | 0.093938 | `proved`, all P0/P1 pass |

Proof: `74a2f1b3d729cbfdc01b291e10769af8eb2a1cb96213993b74302b805d0f19d9`.

## What it is not

- Not a patch generator: the agent works in place; evidence carries the git diff.
- Not isolated: a live agent runs as your OS user (ADR-004). Use trusted repositories until M2.
- Not the verifier: scenarios still judge the change; the independent provider/container is M2.
