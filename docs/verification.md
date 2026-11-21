# Verification and approval boundaries

The gate is the product. This note is the implementation reference for plan §6.8 and ADR-012.

**Status: v4.11 design.** Trusted-base checks, risk rating and observe mode are the next code
changes (T1.20–T1.23). The current gate is deterministic and does not yet enforce all of this.

## Principles

| Principle | Enforcement |
|---|---|
| Checks outlive changes | Policy, flows, scenarios, review rules and risk rules load from the base commit or a trusted checkout, never the worktree |
| Exact commit | Verdict, challenge and approval name a SHA; a new commit invalidates them; merge re-checks the SHA |
| Observe first | Every new rule is `off`, `observe`, then `enforce`; `observe` records `would_block` |
| Risk decides the evidence | Risk rating and code owners decide who and what the release gate needs, never whether the gate exists |
| Run the change | A preview node boots the product and drives a user path; unit tests alone are not verification |
| Bounded repair | Three rounds, then `question.md`; no endless retry |
| Flaky tests are defects | No skip, sleep or retry-to-green; a flake has an owner and an expiry |
| Review the reviewers | Verifier, challenger and risk step are evaluated on incidents and reverts with a clean control |
| Comprehension is evidence | A person explains high-risk and sampled changes; a versioned context pack is part of the run |
| Stop and roll back | One-call rollback, health check, stable window, `works stop --all` |

## Risk rating

```json
{
  "risk": "medium",
  "reasons": ["touches auth/", "5 files", "no migration", "coverage 84%"],
  "owners": ["michael"],
  "rounded_up": true
}
```

- Computed by a separate step, not by the builder.
- Inputs: diff, touched paths, blast radius, reversibility, test coverage, recent incidents.
- Rounds up when unsure.
- `low`: one owner decision with proof and verdict prepared.
- `medium`: one owner decision plus a second reader.
- `high`: named code owner, second reviewer, deeper verification, rollback plan.
- Code owners always approve `auth/`, `billing/`, migrations, secrets, CI/deploy and public API.
- LAIX receives it as `risk`; `requires_approval` follows, but LAIX cannot open the gate.

## Trusted base

- The worktree is the subject, never the judge.
- Verifier code and dependencies run from a separate image or installed copy.
- Scenarios live outside the repository (already true).
- Flows, policy, review rules and risk rules are read from the base commit or trusted checkout.
- A commit that changes a check is routed to a separate task: plan, proof, approval, merge first.
- `run.json` and the proof record `base_sha`, `commit_sha` and `checks_sha`.

## Observe mode

```yaml
mode: observe   # off | observe | enforce
```

- `observe` records a `would_block` event with the rule id and reason.
- Promotion requires a review of false positives over a stated number of changes.
- A rule that cannot be promoted is removed, not left on forever.
- LAIX shadow mode is the same mechanism for a decision, not a special case.

## Run the change

- `preview` node: boot the product, drive one user path, attach screen, log and trace.
- `verify` command per product: versioned, fast, stress-tested like production code.
- Property tests: round-trip, invariants, idempotency, equivalence.
- Differential tests: old system is the oracle for migrations and refactors.
- Cheap checks first; the builder runs tests, build and lint before proposing.

## Repair and flaky tests

- At most three repair rounds; each records a new hypothesis.
- Then `blocked` with `question.md`: what was tried, evidence, hypothesis, options.
- A flake is a `finding` with owner and expiry; fix it or delete the test with a written reason.
- A retry that turns red into green is recorded and does not count as a pass.

## Review the reviewers

- Eval set: historical incidents and reverts, with a size-matched clean control.
- Metrics: recall, false-positive rate, importance (`must-fix`, `should-fix`, `nit`).
- Compare revert rates for changes approved by each path.
- Tune the primary reviewer; later rounds get earlier failures, not another reviewer.
- Verification stamp on every commit: `none | unit | integration | e2e | manual`.

## Comprehension and friction

- High-risk changes and a sample of the rest get a short human explanation in the proof.
- If the person cannot explain the change, it blocks and the plan is revisited.
- Context pack: repo map, architecture notes, glossary, decisions, examples of good changes; hashed
  into the run.
- Friction map: stall, rework and repeated-finding rate per area, compared with a size-matched
  typical change; a brief with evidence, cause, bounded cleanup and a keeping test.

## Operations

- Release: health check, stable window, one-call rollback; a noisy signal cannot roll back every
  pool.
- `works stop --all`: halt new work, leave running tasks resumable.
- Every external action carries an idempotency key; a retry never duplicates a merge, comment,
  release or task.
- No interactive prompt in the engine path; a question becomes a wait with a wake event, deadline
  and default.

## Planned CLI

| Command | Purpose |
|---|---|
| `works risk <task>` | Show the computed risk, reasons and required owners |
| `works gate observe <rule>` | Run a rule in observe mode and list `would_block` |
| `works verify <task>` | Run the preview/verify command and attach evidence |
| `works review <task>` | Review-the-reviewers report for the run |
| `works friction` | Per-area stall and rework map |
| `works rollback <release>` | One-call rollback with a health check |
| `works stop --all` | Stop new work without losing running tasks |
