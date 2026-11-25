# ADR 025 — Ordering is a cost model; a learned ranker must earn it in shadow

Status: proposed, 2026-11-25. (Accepted when M22.6 lands with the promotion guard tested.)

## Context

Once the queue can hold more work than one slot can run, the scheduler has to answer "who goes
first". Three options are on the table:

1. a deterministic rule chain (risk, then budget fragility, starvation, size, age);
2. an optimisation or learned ranker over estimated durations and costs;
3. no ordering at all (FIFO).

We have little data (tens of runs per repository, not thousands), heavy-tailed durations, and a
product where every automated decision must be explainable: the same system records gates, proofs and
audit events. A wrong order costs minutes; a wrong **run** costs money and risk, and most of the
scheduler's value comes from admission control, not from sorting.

## Decision

1. **M21 orders by a deterministic rule chain.** Lexicographic, stable, and the score with its
   components is written to the ledger. A claimed task is never reordered.
2. **Estimates are distributions, not promises.** `p50` is used for ordering, `p90` for fit and budget,
   the mean is used for nothing. Every estimate carries a confidence and a sample count.
3. **Estimates are backtested before they influence anything.** Pinball loss, p90 coverage and tail
   misses per group; a threshold fails CI.
4. **A learned order starts in `shadow`.** It computes and logs its choice, claims nothing, and is
   compared with the rule on our own metrics.
5. **Promotion needs evidence, not preference.** ≥ 4 weeks or ≥ 50 claims, no worse p95 wait, no new
   starvation, no worse `$` per `proved` change, calibration inside the band. Otherwise the answer
   stays `rule`, and the page says why.
6. **Hard floors cannot be learned away.** Anti-starvation (`starvation_boost_hours`), monotonicity in
   risk and age, no preemption, and the two gates stay human regardless of `order.mode`.

## Consequences

- Default behaviour is predictable and testable with property tests; a person can always answer "why
  this one first" in one line.
- The system can improve its ordering **with evidence**, because shadow mode produces the data needed
  to decide, without risking a single run.
- Until M22, big tasks are protected by the age boost and by budget fragility rather than by a
  predicted duration; that is weaker but honest.
- A learned ranker, if it ever ships, is constrained by the same reasons and the same ledger output, so
  it cannot silently invert risk or starve a task.

## Alternatives rejected

- **Pure shortest-job-first.** Optimal only with accurate durations; with noisy estimates it
  systematically postpones large tasks.
- **Pure FIFO.** A three-minute fix waits behind a two-hour run for no reason.
- **Reinforcement learning from the start.** No data, no explainability, and the reward would be
  dominated by noise at this volume.
- **Full optimisation (MILP) now.** One slot and unknown durations make the model's precision
  irrelevant next to the estimation error.
- **Learned order without shadow.** A ranking that cannot be compared with a baseline is a belief, not
  a decision.
