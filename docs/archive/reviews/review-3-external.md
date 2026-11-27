# Review 3 — external critique

An independent reviewer (fresh context, no knowledge of our drafts) read the v2 plan and
`docs/archive/reviews/review-1-self.md`. Findings below are condensed; the plan's v3 changelog records the fixes.

## Blocking issues it raised

1. **Tests are editable by the builder.** `paths.deny` covered only migrations and workflows, so the
   build loop could add `skip`, weaken an assertion, or quarantine the failing test.
2. **The leak guard was unenforceable.** Same host user means the builder can read `../works-scenarios`;
   and the guard covered one run, while traces and prior evidence are readable on the next task.
3. **Verifier specificity was untested.** Mutation only proves sensitivity; a plausible wrong patch
   passing CI was never checked. Builder and verifier on the same provider correlate their blind spots.
4. **Scenarios arrived after the first ship.** M1 shipped before M2 wrote the scenarios that judge it.
5. **No containment.** Host shell with user credentials, no cwd pinning, no network policy, pushes
   possible outside `works publish`.
6. **Release gate unsound.** Prefix matching, `docs/` auto-allow, no `HEAD == approved_commit` check,
   no escape detection despite a 14-day metric.
7. **Proof-over-diff misses non-scenario regressions** — deleted tests, new skips, dependency churn.
8. **One hand-picked issue proves a demo, not a product.** No in-scope rate, n=1 metrics.
9. **No supervisor loop.** Nine manual commands; a crash leaves the task stuck; duplicate webhooks.
10. **Budget checked after the fact**, no wall-clock or CI cap, verifier cost outside the budget.

## Missing entirely

Verifier runtime environment; what the verifier may see; the verdict rule; model id in the trace;
commit-to-run linkage; the other two signal sources; blocked-task handling; fork upkeep; data
retention; a definition of "released".

## Sequencing

Scenarios before build; mutation and calibration before any publish; a manual harness spike in week
one; isolation decided in week 0 rather than left open; escape detection inside M3.

## Verdict

Week 0 and M0/M0.5 are safe and reusable. M1 was not safe: two of the three gates were gameable.

## What changed in v3

See the changelog in the [archived plan](../plans/plan-v4.md). The four fixes the reviewer called necessary are all in:
isolation decided and moved to preconditions, test edits denied with quarantine outside the repo,
specificity and calibration before any publish, and an in-scope rate over 40 real issues.
