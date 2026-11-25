# Reproduce (stage 2)

A task may name a remote and a ref; Works keeps a managed clone, resolves the ref, and still builds
the fix in a separate worktree from that commit.

## Remote and ref

`POST /tasks` accepts `repo_url` and `repo_ref` alongside the local `repo` path.

- clones live under `<home>/repos/<slug>`; a second run fetches instead of cloning;
- `repo_ref` accepts a branch, a tag, a commit SHA, or `pull/<n>` / `pr/<n>` / `#<n>` for a pull
  request (`refs/pull/<n>/head`);
- an unknown ref is a configuration error, never a quiet fallback to the default branch;
- offline mode reuses the cache and fails clearly when the clone is missing.

```bash
works reproduce checkout --url https://github.com/o/r.git --ref pull/7 --json
```

## How to check

`works reproduce detect --repo PATH [--hint TEXT]` chooses, in order:

1. `.works/reproduce.yaml` in the repository (`command: [...]`);
2. a failing test node or a quoted command in the report (advice, never auto-executed);
3. the ecosystem manifest: Python (`pytest`), Node (`npm test`), Go (`go test ./...`), Rust
   (`cargo test`), Java (`mvn test`).

The choice is recorded in the proof with its source (`repo-config`, `signal`, `detected`). Only a
command a person saves on the task is executed; a detected or reported command stays advice.

## Environment

`works reproduce prepare --repo PATH [--offline]` creates the per-repository environment:

- Python: a venv under `<home>/envs/<repo>` and `pip install -r requirements.txt` (or `-e .`);
- Node: `npm ci` when a lockfile exists, `npm install` otherwise;
- Go/Rust/Java: the system toolchain, no install step.

The fingerprint (runtime version and lockfile hashes) is written into the proof either way, so the
reader knows what the check ran with. Installation is explicit; a run never downloads silently.

## Failure classification

A failing check is not automatically the bug:

- a missing module or command is a setup failure and stops with `config_error`;
- a check that fails and then passes on a second run stops with `flaky_test` and is marked
  `stable: no` in the proof;
- a check that passes is `not_reproducible`; a check that fails twice is the confirmed bug.

## Person override

`POST /api/v1/tasks/{id}/reproduction {"command": "python -m pytest tests/test_core.py -q"}` records
the command on the task; the Evidence page also has a **How to reproduce** card with the current
command, its source, attempts, stability, environment and the reporter's hint, plus a field to save
a different command.
