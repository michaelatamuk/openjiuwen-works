# ADR 023 — Bounded repair attempts

Status: accepted, 2026-11-25.

## Context

A build is one engine turn. When the checks fail, the task is blocked and a person decides whether to
run again. That is safe but wasteful: a small mistake in an otherwise correct change needs a manual
round trip, and the next run starts from the same evidence with no record that this was the second
attempt.

## Decision

1. **Retries are opt-in per flow.** `repair.attempts` in the flow YAML is the **total** number of
   build attempts, capped at 3. The default in the shipped flow is 1, so existing behaviour and tests
   do not change.
2. **Only build-caused failures are retryable**: a failing test/preview command and a failed verdict.
   A challenge failure, a policy violation, a flake, a harness error and budget exhaustion stop at
   once; retrying them would hide a real decision.
3. **The state machine allows `checking → building`** for this path only. The verify phase no longer
   calls `_stop` while a retry is still available; it records `build.retry` with the attempt number
   and the reason, and the executor loops back to the builder.
4. **The final attempt stops exactly like before** with `tests_failed` or `verdict_failed`, so the
   blocked state and the evidence remain the same.
5. **Every attempt is visible**: `build.started` carries the attempt number, `build.retry` the reason,
   and evidence records how many attempts were spent.

## Consequences

- Default installs and all existing flows behave as before.
- A flow that wants convergence writes `repair: {attempts: 2}` and gets one extra builder turn.
- Each retry starts from the approved base commit: the worktree is reset and untracked files are
  cleaned, so the second builder turn never inherits a half-applied patch. The first attempt stays
  in the event log and its commands, not in the worktree.
- The engine still cannot approve, release or alter the proof; retries only spend more build budget.
