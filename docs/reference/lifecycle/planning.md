# Planning (stage 3)

The component design, modes and delivery phases are in [planner.md](planner.md).

A plan is a contract, not an essay: every step says what will be done and when it counts as done,
and a person approves the exact version.

## Modes

- **deterministic** (default): one step per flow node, fixed intent/done_when text, commands from the
  flow. No model, no tokens, same input → same plan and hash.
- **shadow**: a model proposal is stored beside the deterministic plan for comparison.
- **assisted**: the model proposal is merged inside the deterministic skeleton; a missing `done_when`
  or command is filled from the skeleton, and the linter still runs.
- **deep**: assisted plus an independent critic; a score below 0.50 blocks the plan.
- **spec**: assisted plus requirements/design/tasks documents.
- **auto**: assisted or deep, chosen from the planned risk.

## What the linter checks

Node coverage, `done_when`, paths (tests and protected paths), destructive commands, budget
estimates, rollback, spec documents, open questions, and a preflight that every command exists and
every scenario script is present. Nothing is executed by preflight.

## Impact

The report's text is scanned for repository paths; test files that import the module or mention the
path become "Impact: …" lines in verification. Named paths with no covering test are recorded in the
plan notes instead of being hidden. This is static, not a call graph.

## Versions and edits

Every draft is a version (`v1/json`, `v2/json`, …) with its own hash: steps, verification, base
commit and checks hash. `PlanStore.diff()` renders `+ / - / ~` between the last two versions.

A person can rework the steps (intent, done_when) and add or remove steps, but only for the nodes the
plan already covers. Saving creates a new draft version, supersedes the previous approval, and
requires a fresh gate decision. The person's comment is appended to the plan notes.

## Budget

The plan carries `estimated_tokens`, `estimated_usd` and `estimated_minutes`; a value over the task
budget is a lint error before the gate. Evidence records the estimate next to the actual usage, so
the next plan can be calibrated against reality.
