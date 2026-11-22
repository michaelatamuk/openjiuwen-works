# agent-core verification team

Works uses agent-core on two levels:

1. **Harness** — `--live` drives `openjiuwen.harness_protocol` from the agent-core checkout.
2. **Verification team** — `works team verify` runs a deterministic three-role team on
   `BaseTeam` + `TeamRuntime`.

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

## Boundary

- The team has no tools, no model and no write access to the worktree.
- It cannot open a gate; a person still approves release.
- If agent-core is unavailable, the command fails with a configuration error instead of falling
  back silently.
- The next step is to run this team inside the isolated verifier runtime (`--verifier docker`), not
  the host environment.
