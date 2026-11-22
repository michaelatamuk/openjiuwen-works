# JiuwenSwarm: an isolated builder boundary

JiuwenSwarm is a multi-agent platform, not a patch library. It carries its own runtime, gateway,
A2A server, tool approvals, model configuration and a pinned `openjiuwen` commit. Installing it
inside the Works virtualenv would replace the builder Works already has and break the verifier.

So Works treats it as an **external builder** behind a contract.

## Contract

```
works  ->  request.json  ->  entrypoint  ->  result.json  ->  works
```

The entrypoint is a separate process. It receives:

| Argument | Meaning |
|---|---|
| `--works-kind propose` or `challenge` | which answer to produce |
| `--works-request PATH` | JSON request (task, source, worktree, base commit) |
| `--works-result PATH` | where to write the JSON answer |

Proposal result:

```json
{
  "patch": "diff --git ...",
  "applied": true,
  "touched_paths": ["src/app.py"],
  "model": "jiuwenswarm",
  "provider": "jiuwenswarm",
  "tokens": 0,
  "usd": 0.0,
  "notes": [],
  "stop": null
}
```

Challenge result:

```json
{ "allow": false, "reason": "no test covers the failure", "concerns": ["coverage"] }
```

## Usage

```bash
works swarm doctor
works swarm doctor --python C:\path\to\python.exe --home C:\path\to\jiuwenswarm --json
works run <task> --swarm
```

`works run --swarm` refuses to start unless the preflight succeeds. There is no fallback to a fake
proposal: a builder that cannot run must fail as a configuration error.

## Why the local CLI is not enough

The checkout at `C:\Workspace\openjiuwen\jiuwenswarm` currently fails before its own parser:

```
ModuleNotFoundError: No module named 'agent_gateway'
```

Its pinned dependencies also conflict with the Works environment. The supported shape is therefore
an isolated venv or container plus a small adapter that translates this contract to JiuwenSwarm's
A2A/CLI. Set `WORKS_SWARM_ENTRYPOINT` to the adapter's JSON argv.

| Variable | Default |
|---|---|
| `WORKS_SWARM_PYTHON` | `C:\Workspace\openjiuwen\jiuwenswarm\.venv\Scripts\python.exe` |
| `WORKS_SWARM_HOME` | `C:\Workspace\openjiuwen\jiuwenswarm` |
| `WORKS_SWARM_ENTRYPOINT` | `["-m", "jiuwenswarm.channels.cli.main", "--help"]` |

## Boundary

- The worktree is the only shared path.
- The adapter may edit the worktree, like the current live harness; policy runs afterwards.
- Works does not import JiuwenSwarm and does not inherit its dependency tree.
- The builder still cannot open a gate or write the release packet.
