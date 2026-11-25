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

## Not in this pass

- **Retry loop.** One bounded builder turn per run; a failed check stops with a typed reason and a
  person decides whether to run again. A repair loop needs its own crash and convergence tests.
- **Network isolation.** Paths and commands are constrained, but denying network access to the
  engine needs an OS sandbox (container or firewall); until then that remains a deployment control,
  not a claim.
