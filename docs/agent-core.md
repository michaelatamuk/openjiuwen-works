# agent-core verification team

Works uses agent-core on three levels:

1. **Harness** — `--live` drives `openjiuwen.harness_protocol` from the agent-core checkout.
2. **Verification team** — `works team verify` runs a deterministic three-role team on
   `BaseTeam` + `TeamRuntime`.
3. **Ask Mira** — the Thread view asks a real `openjiuwen` model about one recorded run; the answer
   streams into the worklog as an advisory message.

The team is intentionally **model-free**. It reads recorded evidence, not agent prose:

| Role | Job |
|---|---|
| **Inspector** | policy, verdict, challenge, proof hash, commit presence |
| **Challenger** | high risk and residual `not_tested` gaps |
| **Reporter** | combines both and returns `allow` or `block` |

No API key is needed. A language model is not a verifier; it can be an advisory reviewer in a later
layer, but it cannot change the verdict.

## Run

```bash
works team verify <task-id>
works team verify <task-id> --json
```

The command reads the latest `run.json` and `evidence.json`, invokes agent-core's Python in a
subprocess (so Works does not inherit agent-core's full dependency tree), and records
`team.verified` on the task.

Environment:

| Variable | Default | Meaning |
|---|---|---|
| `WORKS_AGENT_PYTHON` | `C:\Workspace\openjiuwen\agent-core\.venv\Scripts\python.exe` | agent-core interpreter |
| `WORKS_AGENT_CORE` | `C:\Workspace\openjiuwen\agent-core` | agent-core checkout on `PYTHONPATH` |

## Ask Mira

`Ask Mira` is a real model call, not a template. The browser posts to `/api/ask/stream`; the server
builds a context from the task, run, evidence, release packet, delivery and confirmation, then
starts `scripts/agent_chat_worker.py` with agent-core's Python. The worker uses openjiuwen's
`Model` (`Anthropic` client against an Anthropic-compatible endpoint) and streams text back as SSE.

Every answer is stored as `thread.agent` with the question, answer, model, tokens and USD. The
system prompt forbids inventing evidence: if the context does not contain an answer, Mira says
"Not recorded in this run." The answer is advisory and cannot approve, release, retry or change a
task. Each request carries the last three recorded question/answer pairs as conversation history,
so a follow-up question keeps the earlier answer in view.

Two further model layers work over the same recorded context. `Generate commentary` stores three
short messages as `thread.commentary` (builder, inspector, reporter). `Team discussion` stores
three messages as `thread.discussion` (inspector, challenger, reporter), each with an optional
`support` / `concern` / `block` stance. Both are marked `generated: true`, read only recorded
evidence, and are advisory text: they are not evidence and cannot change a verdict or a gate.

Environment:

| Variable | Default | Meaning |
|---|---|---|
| `WORKS_MODEL_KEY` / `ANTHROPIC_API_KEY` | — | model credential; required |
| `WORKS_MODEL_BASE` | `https://api.deepseek.com/anthropic` | Anthropic-compatible endpoint |
| `WORKS_AGENT_MODEL` | `deepseek-chat` | model name |
| `WORKS_AGENT_PYTHON` | agent-core venv Python | isolated interpreter |
| `WORKS_AGENT_CORE` | `C:\Workspace\openjiuwen\agent-core` | runtime on `PYTHONPATH` |

Without a key or runtime the composer is disabled with the reason; there is no fake answer.

## Boundary

- The team has no tools, no model and no write access to the worktree.
- It cannot open a gate; a person still approves release.
- If agent-core is unavailable, the command fails with a configuration error instead of falling
  back silently.
- The next step is to run this team inside the isolated verifier runtime (`--verifier docker`), not
  the host environment.
