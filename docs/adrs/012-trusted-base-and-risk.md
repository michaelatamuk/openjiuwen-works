# ADR-012 — Checks outlive changes; risk decides who approves

**Status:** accepted · 2026-11-21

## Context

The 2026 software-factory material converges on one lesson: generation is no longer the bottleneck;
verification and approval are. Runway's line works because risk-rated approval, preview
environments, exact-commit gates and rollback were built before autonomy was handed over. The Claude
Code team's practice adds the sharpest rule: **a change cannot edit the check that judges it** —
review rules are read from the base branch, never from the pull request. NBER's independent evidence
shows task output rising far faster than shipped releases, which is what a weak verification layer
looks like at scale.

Works dogfoods on its own repository. That makes "checks outlive changes" existential: the builder
could otherwise edit `policy.py`, a flow, a scenario or a review rule and pass its own gate. The
builder is also the party being judged, so a gate that reads the worktree is not a gate.

## Decision

- **Trusted base.** Policy, flows, scenarios, review rules, reliability checks and risk rules load
  from the base commit or a trusted checkout, never from the worktree. Verifier code and its
  dependencies run from a separate image or installed copy. Changing a check is a separate task with
  its own plan, proof and approval.
- **Exact commit.** A verifier result, challenger verdict or approval names the SHA it was given for.
  A new commit invalidates all three; the merge re-checks the exact SHA.
- **Risk rating.** A separate risk step rates each change `low | medium | high`, rounding up when
  unsure, from diff, paths, blast radius, reversibility, coverage and recent incidents. Code owners
  always approve `auth/`, `billing/`, migrations, secrets, CI/deploy and public API. The rating never
  removes the two human gates; it decides the evidence and the reviewers. LAIX consumes it as its
  `risk` input.
- **Observe before enforce.** Every new policy rule, flow node, risk rule and review check has
  `off | observe | enforce`. Observe records `would_block` with a reason; promotion follows a
  false-positive review. LAIX shadow mode is one instance.
- **Run the change.** A `preview` node boots the product and drives one user path; a per-product
  `verify` command is versioned and stress-tested. Property tests cover invariants; differential
  tests compare old and new systems on generated or sampled inputs.
- **Bounded repair and flaky tests.** At most three repair rounds, then `question.md` with evidence,
  hypothesis and options. A test that passes only on retry is a defect; no skip, sleep or
  retry-to-green.
- **Review the reviewers.** Evaluate verifier, challenger and risk step on historical incidents and
  reverts with a size-matched clean control; track recall, false positives and importance. Tune the
  primary reviewer; do not stack reviewers.
- **Comprehension sample.** Every high-risk change, and a sample of the rest, gets a short human
  explanation in the proof. If nobody can explain it, the change blocks and the plan is revisited.
  A versioned context pack (repo map, architecture, glossary, decisions, examples) is hashed into
  the run.
- **Safe operations.** Release carries a health check, a stable window and a one-call rollback; a
  noisy signal cannot roll back every pool. `works stop --all` halts new work and leaves running
  tasks resumable. External actions carry idempotency keys; the engine never waits on an interactive
  prompt.

## Consequences

- The verifier becomes a versioned, tested product component, not a script inside the change.
- Risk rating adds one role and one artifact; it makes the release gate faster for low-risk changes
  without removing the person.
- Observe mode delays enforcement by one evidence cycle; it prevents a new rule from becoming a
  silent gate.
- A new commit is more expensive because the gate re-runs; that is the correct cost.
- Comprehension samples consume human time; they are the counterweight to review-by-dashboard.
- Flaky tests and gate false positives become first-class findings, so the verification layer can
  be tuned rather than trusted blindly.

## Alternatives rejected

- **Read checks from the worktree**: lets the change grade itself, especially under dogfooding.
- **Trust an approval across commits**: a verdict on an old SHA says nothing about the merged code.
- **Approve by AI for low risk now**: the public evidence is self-reported; the two gates stay until
  our own evals and a green escape window justify otherwise.
- **Enforce every new gate immediately**: produces false-positive outages and teaches people to
  bypass the gate.
- **Add more reviewers**: cost rises faster than recall; tune the primary and give later rounds
  earlier failures.
- **Measure lines, PRs or tokens**: inputs are easy to increase and easy to game; shipped changes and
  reverts are the pair that matters.
