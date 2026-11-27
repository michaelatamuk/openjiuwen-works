# Build (stage 5)

The engine runs inside the untouched copy of the approved base commit. Works observes the worktree,
not the engine's summary: changed files come from git, and every command the engine runs through the
runner is recorded.

## Before the turn

- The per-run budget is checked after the turn (tokens, USD, wall clock) and the **daily** ceiling is
  checked before the engine starts, so an over-budget day never spends another call.
- The plan gate must be current: an expired or hash-mismatched approval stops the run with
  `needs_plan_approval`.
- The worktree is created from the approved base commit; the engine has no path to the gates, the
  evidence or the release.

## During the turn

- `build.started` / `build.finished` events bracket the turn; the run shows a heartbeat while the
  engine works, and Cancel kills the process tree (Windows Job Object, Linux `PR_SET_PDEATHSIG`).
- The transcript (`transcript.json`) keeps the model, provider, adapter version, prompt name and hash,
  token/USD cost, notes and the engine's trace. It is listed as an evidence artifact.
- No change is a stop (`no_change`/harness failure), never a success.

## After the turn

The touched paths are collected from git, diffed and rated; policy and plan deviations are evaluated
against the approved plan. A file outside the plan's named write scope becomes a `plan.deviation`
event; a denied path is a `policy_violation`.

## Repair attempts

`repair.attempts` in the flow is the total number of build attempts (capped at 3, default 1). Only a
failing test/preview or a failed verdict is retryable; a challenge failure, policy violation, flake,
harness error or budget stop ends the run at once. Each retry starts from the approved base commit:
the worktree is reset and untracked files are removed, so a half-applied patch is never inherited. The
last attempt stops with the usual `tests_failed`/`verdict_failed`, and evidence records `attempts`.

## Not in this pass

- **Network isolation.** Paths and commands are constrained, but denying network access to the
  engine needs an OS sandbox (container or firewall); until then that remains a deployment control,
  not a claim.
