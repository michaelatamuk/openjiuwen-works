# Live harness

`works run --live` uses the real builder through an `openjiuwen` harness. The default provider is
Claude Code on an Anthropic-compatible endpoint; `dsh` (DeepSeek Harness) and `codex` are selectable
when their SDKs are installed. The provider is recorded separately from the model provider.

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
| `WORKS_HARNESS_PROVIDER` | `claudecode` | `claudecode`, `dsh` or `codex` |
| `WORKS_VERIFIER_HARNESS_PROVIDER` | builder provider | separate challenger provider |
| `WORKS_DSH_HOME` | required for `dsh` | DeepSeek Harness home; never falls back to `~/.dsh` |
| `WORKS_DSH_PROVIDER` | `deepseek-official` | DSH model provider label |
| `WORKS_CODEX_PROVIDER` | `deepseek` | Codex model provider label |

`dsh` needs the `deepseek_harness` SDK; `codex` needs `openai_codex` or a Codex CLI. A missing SDK is
a configuration error, never a fake build. The `native` DeepAgent provider is not wired into Works
yet because it needs a full `DeepAgentSpec` (tools, workspace, rails), not just a model key.

`ANTHROPIC_BASE_URL` in the shell may point elsewhere; the harness injects the explicit
`--model-base` through the CLI settings layer, so the run is reproducible. The variable name is a
Claude Code compatibility name: the endpoint and model decide the actual provider.

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

The challenger prompt is `flows/fix-issue/prompts/challenge.md`. It runs in a separate session with
`permission_mode="plan"`: the challenger may read and run `git diff`, but may not edit. It must reply
with one JSON object (`allow`, `reason`, `concerns`); anything else fails closed and blocks the task.
The proof records the challenge, its concerns and the prompt hash.

## Measured on the development host

| Run | Time | Tokens | USD | Result |
|---|---|---|---|---|
| Builder only (`LIVE-2`) | 115.6 s | 104 563 | 0.093938 | `proved`, no challenger |
| Builder + challenger (`LIVE-4`) | 88.6 s | 180 604 | 0.192889 | `proved`, challenge ALLOW |

Builder proof: `74a2f1b3d729cbfdc01b291e10769af8eb2a1cb96213993b74302b805d0f19d9`.

The challenger runs in a **disposable git worktree** with the builder's diff applied. It cannot
touch the builder's worktree; its edits, if any, are discarded with the worktree. It can use a separate verifier provider through
`WORKS_VERIFIER_MODEL`, `WORKS_VERIFIER_BASE` and `WORKS_VERIFIER_API_KEY`; `run.json` and the
proof record the verifier provider and whether the split held.

## What it is not

- Not a patch generator: the agent works in place; evidence carries the git diff.
- Not isolated: a live agent runs as your OS user (ADR-004). Use trusted repositories until M2.
- Not the verifier: scenarios still judge the change; the challenger can use a separate provider and
  the container verifier is a separate boundary.
