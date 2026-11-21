# Verification and approval boundaries

The gate is the product. This note is the implementation reference for plan §6.8–§6.9 and
ADR-012/013.

**Status: v4.13.** Trusted-base checks, risk rating, observe mode, flake enforcement and the
decision port are in. Agent readiness, feature map, architecture guardrails and the verification
cost split are next (T2.18–T2.19, T1.25).

## Principles

| Principle | Enforcement |
|---|---|
| Readiness before autonomy | Lint, format, types, fast tests, architecture, suppressions, `verify` and a feature map must pass before a flow runs |
| Checks outlive changes | Policy, flows, scenarios, review rules and risk rules load from the base commit or a trusted checkout, never the worktree |
| Every correction becomes a check | Repeated findings, escapes and reverts become a lint rule, structural test, API change or scenario |
| Exact commit | Verdict, challenge and approval name a SHA; a new commit invalidates them; merge re-checks the SHA |
| Observe first | Every new rule is `off`, `observe`, then `enforce`; `observe` records `would_block` |
| Risk decides the evidence | Risk rating and code owners decide who and what the release gate needs, never whether the gate exists |
| Run the change | A preview node boots the product, drives a user path and attaches artifacts; unit tests alone are not verification |
| Feature coverage is evidence | A versioned feature map drives preview and the proof shows covered and uncovered features |
| Bounded repair | Three rounds, then `question.md`; no endless retry |
| Flaky tests are defects | No skip, sleep or retry-to-green; a flake has an owner and an expiry |
| Review the reviewers | Verifier, challenger and risk step are evaluated on incidents and reverts with a clean control |
| Comprehension is evidence | A person explains high-risk and sampled changes; a versioned context pack is part of the run |
| Stop and roll back | One-call rollback, health check, stable window, `works stop --all` |

## Trust pyramid and agent readiness

Strongest first: deterministic code (APIs, architecture, lint, types, compilers, tests), then
verification (runtime, property, formal), then prose (rules, skills, `AGENTS.md`, comments).

`works readiness` refuses automation until:

- lint, format and types pass;
- the fast test path is green;
- import boundaries and structural tests pass;
- no unowned suppression is present;
- a `verify` command and a feature map exist.

A red gate produces the missing check, not another prompt. The codebase is the agent's largest
input: a repeated correction becomes a check, and old occurrences are cleaned up.

## Risk rating

```json
{
  "risk": "medium",
  "reasons": ["touches auth/", "5 files", "no migration", "coverage 84%"],
  "owners": ["michael"],
  "required_reviewers": 2,
  "deeper_verification": false,
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

## Feature map and runtime artifacts

- `features/<product>.yaml`: id, user-facing name, path or command, selectors, expected observation.
- The preview drives a feature id and attaches screenshot, video, log and trace.
- The proof shows covered and uncovered features; a stale id fails the scenario.
- Review reads artifacts, not every diff.

## Architecture guardrails

- Import boundaries and dependency-graph rules live in the repository.
- Module fan-in and structural tests run in the verifier.
- A new suppression (`noqa`, type ignore, lint disable, skip, xfail) needs an owner, reason and
  expiry; it is a suspicious change.
- Workaround comments and new timers are flagged, not silently accepted.

## Verification cost

- `run.json` splits builder, challenger and verifier tokens/USD.
- The proof reports the verification share next to the total.
- A mature line often spends most tokens on verification; this is a measurement, not a target.

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
| `works readiness [--repo PATH]` | Check whether a repository is ready for automation |
| `works feature list` | Show the feature map and coverage |
| `works risk <task>` | Show the computed risk, reasons and required owners |
| `works gate report` | Decisions, `would_block`, disagreements |
| `works verify <task>` | Run the preview/verify command and attach evidence |
| `works review <task>` | Review-the-reviewers report for the run |
| `works friction` | Per-area stall and rework map |
| `works rollback <release>` | One-call rollback with a health check |
| `works stop --all` | Stop new work without losing running tasks |
