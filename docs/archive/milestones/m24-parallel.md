# M24 — parallel tasks in one repository (design)

> **Doc status:** archived · **Owner:** Michael · **Last reviewed:** 2026-11-26

Status: complete (24.1–24.5). The gap was narrower than the first estimate: a worktree per run and a
job pool already existed. M24 makes the scheduler honour the `per_repo` slot it documents.

## Why

The scheduler can already claim up to `concurrency.global` tasks per tick, and the daemon submits each
claim as a job. Two things still serialize work:

1. selection refuses **any** second task in a repository (`repo_busy`), ignoring `per_repo`;
2. a tick computes the remaining budget once, so several claims can each spend the whole remainder.

A team with five open bugs in one service gets one run at a time and a queue that looks stuck.

## What already exists

| piece | where |
|---|---|
| One worktree per run (`worktrees/<run_id>/repo`) | `application/supervisor/execution.py` |
| One branch per task (`works/<task_id>`) | `application/delivery/deliver.py` |
| Leases with a TTL per task | `application/scheduling/lease.py` |
| Job pool with a worker per slot | `interfaces/api/jobs.py`, `wiring.py` |
| Global and per-repo slots in policy | `application/scheduling/policy.py` |
| Disk, job-pool, API-load and provider guards | `application/scheduling/select.py` |

Nothing new is needed for isolation. The work is selection, reservation and the honest limits.

## Decision

- **`per_repo` is a count, not a boolean.** `Signals.active_by_repo` carries the number of active
  leases per repository; selection refuses only when that count reaches `policy.concurrency.per_repo`.
  The default stays `1`, so an existing install behaves exactly as before.
- **Recommended ceiling is 3.** Above that, one machine spends more time swapping worktrees, builds and
  provider calls than finishing changes. The policy accepts any positive integer; the docs recommend
  1–3 and `global` no higher than the job pool.
- **Budget is reserved across claims in one tick.** After each claim, its `p90_usd` is subtracted from
  the remainder used for the next candidate. A tick cannot promise the same dollars twice.
- **The pool is sized from the policy at startup.** `job_workers` reads `concurrency.global`, clamps it
  to 2–8, and the daemon logs the choice. Changing the policy's global slots needs a restart; the
  scheduler status shows both numbers.
- **Isolation is unchanged and required.** Each run gets its own worktree from the same base commit;
  delivery uses a branch named after the task. Two runs never share a tree or a branch.
- **No preemption.** A started run finishes. Parallelism is admission control, not time-slicing.

## Safety

- The main checkout stays clean and read-only; runs only write inside their worktree.
- Two worktrees from one repository at the same commit are independent; a later delivery conflict is a
  normal human merge decision, not a corrupted run.
- The daily budget, per-run cap, global slots, disk floor and machine-load guards all still apply per
  claim; the reservation only makes the budget stricter.
- A repository lock is no longer global, so `repo_busy` now means "the policy's per-repo slots are
  full", not "someone touched this repo".

## Non-goals

Cross-repository coordination, a distributed queue, preemption, per-branch locks and automatic conflict
resolution.

## Acceptance

- default `per_repo: 1` still refuses a second task in the same repository;
- `per_repo: 2` claims two tasks in one repository in one tick;
- a tick with a $3 remainder and two $2.50 estimates claims one and records `budget_exhausted` for the
  other;
- two runs produce two worktree paths and two task branches (existing isolation tests);
- the job pool is at least the global slots (unit test on `job_workers`);
- `mypy`, the scheduling suite and the docs link check stay green.

## Work breakdown

| item | days |
|---|---|
| 24.1 per-repo counts in signals and selection | 1 |
| 24.2 budget reservation across claims | 0.5 |
| 24.3 pool sizing and status | 0.5 |
| 24.4 tests and docs | 1 |
| **total** | **3 (~4 with contingency)** |
