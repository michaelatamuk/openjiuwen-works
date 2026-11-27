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
| `--works-request PATH` | JSON request (task, source, worktree, base commit, approved plan brief) |
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

## Adapter

`scripts/swarm_adapter.py` is the repo's `works.swarm.v1` entrypoint. A source checkout uses it by
default, so `works swarm doctor` probes the adapter and `works run --swarm` calls it with the
request/result files.

For `propose` the adapter runs the JiuwenSwarm chat CLI in the disposable worktree, then returns
`git diff HEAD` and the touched paths. For `challenge` it asks for one JSON verdict, refuses a
review that modifies the worktree, and fails closed when no machine-readable verdict arrives.

The adapter is stdlib-only. It never imports JiuwenSwarm into the Works environment.

| Variable | Default |
|---|---|
| `WORKS_SWARM_PYTHON` | `C:\Workspace\openjiuwen\jiuwenswarm\.venv\Scripts\python.exe` |
| `WORKS_SWARM_HOME` | `C:\Workspace\openjiuwen\jiuwenswarm` |
| `WORKS_SWARM_ENTRYPOINT` | the repo's `scripts/swarm_adapter.py` when present, else the CLI help probe |
| `WORKS_SWARM_CLI` | `python -m jiuwenswarm.channels.cli.main` (JSON argv override for tests or wrappers) |
| `WORKS_SWARM_TIMEOUT` | `1800` seconds |

A live run still needs the JiuwenSwarm gateway/model configuration and an isolated venv. The
protocol is tested on a fixture repository with a fake CLI; the live model is not part of CI.

## Boundary

- The worktree is the only shared path.
- The adapter may edit the worktree, like the current live harness; policy runs afterwards.
- Works does not import JiuwenSwarm and does not inherit its dependency tree.
- The builder still cannot open a gate or write the release packet.
