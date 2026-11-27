# Runbook

> **Doc status:** active · **Owner:** Michael · **Last reviewed:** 2026-11-27

Known failures and the first response. Every entry says what the operator sees, why it happens,
and what to do — no narration, no guesses.

## The one way to run it

```bash
works daemon start --write
```

Then open **http://127.0.0.1:8765/**. The home is always `~/.works`
(`C:\Users\<you>\.works` on Windows), whatever directory you start from; `--home` exists for tests
and isolated demos, not for daily use. Viewing needs no token on loopback; a token is only for
changing things from another device (`works daemon pair`).

## `git apply: patch does not apply`

**See:** the run stops with `conflict` and the task becomes `blocked`; `evidence.md` says `BLOCK`.

**Why:** the worktree file does not match the patch context. The usual cause on Windows is CRLF
in the worktree while the patch uses LF, or a base commit that moved after the proposal.

**Do:**
1. `git -C <repo> config core.autocrlf false` and `core.eol lf`; re-init the fixture if needed.
2. Confirm the worktree base equals `plan.drafted.base_commit` in `queue/<task>/events.jsonl`.
3. Replay the trace, or start a new task from the current `main`.

## `conflict`: `task ... is owned by ...`

**Why:** a previous supervisor died without releasing its claim.

**Do:** confirm no `works run` is active for that task, then delete
`queue/<task>/owner` and start again. The event history is untouched; the task resumes from its
last recorded state.

## `conflict`: `has uncommitted changes`

**Why:** the product repository must be clean before a run; the base commit is pinned.

**Do:** commit or stash, then `works run` again. Never run the factory on a dirty tree.

## `config_error`: `no harness configured`

**Why:** neither a recorded trace nor the live harness was selected.

**Do:** pass `--trace fixtures/traces/fix-add.json` for a deterministic run, or `--live` with
`ANTHROPIC_API_KEY` and an openjiuwen installation. See `docs/guides/integrations/live-harness.md`.

## The live harness refuses `claude.CMD`

**See:** `Refusing to execute batch script ... Use a native claude executable instead`.

**Why:** the Claude Agent SDK refuses `.cmd`/`.bat` on Windows because `cmd.exe` cannot escape
arguments.

**Do:** leave `CLAUDE_CLI` unset and let the SDK use its bundled `claude.exe`, or point
`CLAUDE_CLI` at the npm package's `bin\claude.exe`.

## A live agent edited a test file

**See:** `proved` does not happen; stop reason `policy_violation` lists the path.

**Why:** policy is enforced after the turn (the agent edits the worktree directly) and before
tests; the worktree is disposable.

**Do:** inspect the worktree, discard it, and start a new task. Instructions already forbid test
edits; this is detection, not prevention until the M2 container.

## A task waits on the wrong event

**See:** `task … waits on 'ci_passed', not 'ci_failed'`.

**Why:** a wake must match the subscription recorded when the task started waiting.

**Do:** send the recorded event, or let the deadline/default move the task. Do not edit the event
file; if the subscription is wrong, start a new wait from a state the machine allows.

## A dispatch conflict

**See:** `task … is owned by …` and that task is skipped for this pass.

**Why:** another dispatcher or supervisor holds the claim.

**Do:** nothing if the other process is alive; it will release the claim. If it died, follow the
dead-owner procedure above. `works dispatch` never runs a claimed task twice.

## A writable daemon owns the home

**See:** `a writable daemon owns …; use --daemon or works daemon stop`.

**Why:** one process owns runs and jobs for a home. A second writable daemon would race the queue
and the worktrees.

**Do:** route the command through the daemon (`works run --daemon`, `works dispatch --daemon`),
or stop it first. `works ui --write` takes the same lock and also counts as the owner.

## `daemon start` or `daemon stop` does not settle

**See:** `the daemon did not become healthy`, `no daemon is running`, or a stop that reports a pid
still alive.

**Why:** a stale `daemon.json`, a port already in use, or a process that is not answering with this
home's health identity.

**Do:**
1. `works daemon status` — a dead pid clears the identity file; a foreign home is not adopted.
2. Read `.works/state/daemon.log`; a bind failure or import error is at the end.
3. `works daemon stop` posts `/admin/shutdown` with the token. It only signals/kills a pid that
   still answers with this home's `/health`; never kill a pid by hand without that check.
4. If a hung process keeps the port, stop it from Task Manager and start again. The recorded pid is
   the daemon's own, not the Windows venv launcher.

## A job timed out or was cancelled

**See:** `error_code: timeout`, or `status: cancelled` after `DELETE /jobs/{id}`.

**Why:** `WORKS_JOB_TIMEOUT` expired, or a person cancelled the job. A late builder result cannot
overwrite the final status.

**Do:** inspect the job log tail, fix the cause (a long build, a hung command), then re-run. Cancel
kills the child process tree; if a third-party process outlives it, check `daemon.log`.

## The token leaked

**Do:** call `POST /api/v1/admin/rotate-token` with the current bearer token (or use the Settings
surface once it exposes it). The old bearer and every session cookie stop working; the CLI reads the
new `.works/state/http-token` on its next run. Do not commit the token file.

## `config_error`: `a scenario set is required`

**Why:** scenarios are written before the build; the plan cannot be judged without them.

**Do:** pass `--scenarios <path>/fix-add.yaml`. The file and its scripts must live outside the
target repository.

## A legitimate change is denied by policy

**Why:** deny wins, and the defaults (tests, migrations, workflows, scenarios) cannot be loosened
by a flow. That is the point.

**Do:** narrow the change. A human override is deliberately not implemented; a policy change is a
reviewed commit to `DEFAULT_DENY` or the flow, with an ADR if it changes a decision.

## `index.sqlite3` is corrupt or stale

**See:** `status` falls back to `task.json`, or the command reports no tasks while directories
exist.

**Why:** the index is a cache, not the source of truth.

**Do:** `python -c "from works.adapters.queue.store import Queue; from works.config import load_paths; Queue(load_paths()).rebuild_index()"`.
Deleting `queue/index.sqlite3` is also safe; it is rebuilt on the next write.

## Windows briefly denies replacing a projection

**See:** a warning about a locked `task.yaml`, retried ten times.

**Why:** a scanner or indexer holds a freshly written file for a few milliseconds.

**Do:** nothing if the retry succeeds. If it persists, exclude the workspace directory from
real-time scanning; the code retries, it does not ignore the failure.

## The verifier cannot run

**See:** the task is `blocked`, never `proved`.

**Why:** a missing verifier is not a pass. The supervisor does not degrade to "trust the builder".

**Do:** fix the container or provider, then start a new task. Blocked is terminal in v0 by design.

## Back up or move a home

**Do:** `works --home <home> backup --out works-backup.tar.gz`. The archive contains `queue/`,
`runs/`, `flows/`, `ledger.jsonl` and the workspace settings; it deliberately excludes
`.works/state` (tokens, device hashes, job journals) and `worktrees/` (disposable).

**Restore:** `works --home <new-home> restore --from works-backup.tar.gz`. A non-empty home needs
`--force`; the restore replaces queue/runs/flows and keeps the destination's own state directory.

## Job journals grow without bound

**Do:** `works --home <home> prune-jobs --days 30 --json`. Finished jobs older than the window are
reduced to one summary line each in `.works/state/jobs-archive.jsonl` and their JSON files are
deleted; queued or running jobs are never pruned. Run it with `--dry-run` first.

To collect evidence before pruning, or for any bug report, use
`works --home <home> doctor --bundle works-debug.tar.gz`: versions, daemon identity, job summaries,
index health, disk usage and log tails, with no tokens, cookies or device hashes.

## A job was killed by a restart

A restart marks the job `failed` with `daemon restarted while the job was running` and releases the
task owner. Nothing resumes automatically; start a fresh `works run` after checking the worktree and
remote state. See `docs/reference/platform/reliability.md`.

## Start the daemon at logon on Windows

Two supported recipes; pick one and verify it survives a reboot.

**Task Scheduler** (no extra software):

```text
schtasks /Create /SC ONLOGON /TN "openJiuwen Works" /TR ""C:\path\to\.venv\Scripts\python.exe" -m works daemon start --write"
```

**NSSM** (a real Windows service, restart on crash):

```text
nssm install openJiuwenWorks "C:\path\to\.venv\Scripts\python.exe"
nssm set openJiuwenWorks AppParameters "-m works daemon start --write"
nssm set openJiuwenWorks AppDirectory "C:\path\to\workspace"
nssm set openJiuwenWorks Start SERVICE_AUTO_START
nssm start openJiuwenWorks
```

Verify start, health and stop before trusting it:

```powershell
works --home C:\path\to\workspace daemon status --json   # running + the URL another machine can open
Invoke-WebRequest http://127.0.0.1:8765/api/v1/health/live | Select-Object StatusCode
works --home C:\path\to\workspace daemon stop --json      # waits for the pid, not just the socket
```

A remote bind additionally needs `--allow-remote --trusted-host` and private ACLs on `.works/state`.
The Windows CI job runs `scripts/smoke_daemon.py`, which covers start → dispatch → kill mid-run →
restart reconciliation → graceful stop.
