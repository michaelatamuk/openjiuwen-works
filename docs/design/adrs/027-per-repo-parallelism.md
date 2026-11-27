# ADR 027 — Per-repository parallelism behind a slot count

Status: accepted, 2026-11-26 (M24.1–M24.4 landed with tests). Revisits one rejected alternative in
ADR 024.

## Context

ADR 024 rejected per-repository parallelism because it looked like extra moving parts: separate
worktrees, a concurrent scheduler and more ways to corrupt a run. Since then the cost changed:

- every run already gets its own worktree (`worktrees/<run_id>/repo`), so two runs cannot share a tree;
- delivery already uses one branch per task (`works/<task_id>`), so two deliveries cannot collide;
- the daemon already submits each claim as a job to a pool, so execution is concurrent by design.

What remained was a selection rule that refused **any** second task in a repository, and a budget
check that could promise the same dollars to several claims in one tick.

## Decision

1. **`per_repo` is honoured as a count.** Active leases are grouped by repository; a task is refused
   only when its repository already holds `policy.concurrency.per_repo` leases. The default stays 1.
2. **The recommendation is 1–3.** More slots on one machine trade throughput for worktree churn, build
   contention and provider rate limits. The policy accepts any positive integer; the reference
   recommends a small number.
3. **Budget is reserved per claim inside a tick.** Each claim subtracts its `p90_usd` from the remainder
   used for the next candidate, so a tick cannot overspend the daily budget by claiming N tasks at once.
4. **The pool follows the policy at startup.** `job_workers` reads `concurrency.global`, clamps it to
   2–8, and the status shows both the policy slots and the pool size. A change needs a restart; no
   silent resize.
5. **No preemption, no shared tree, no shared branch.** A started run finishes. Parallelism changes
   admission, not the lifecycle.

## Consequences

- A repository with several independent reports can make progress on more than one at a time, which is
  the metric a team with a backlog actually feels.
- `repo_busy` changes meaning from "this repository is in use" to "its slots are full". The reason code
  stays the same so existing dashboards and tests keep working.
- Two runs at the same base commit may later produce two approved changes that conflict. That is a
  merge decision for a person; the factory never resolves it silently.
- A larger `global` without a matching pool would park claims in the executor while their leases age.
  The startup sizing removes that trap; the clamp at 8 keeps one laptop from being asked to run twenty
  builds.
- The budget is stricter than before, never looser: a burst of claims now sees the remainder shrink
  claim by claim.

## Alternatives rejected

- **Keep one task per repository.** Simple, but it makes the queue a lie: work is ready and nothing
  runs.
- **Global parallelism only.** Two repositories run in parallel, one repository still serializes; the
  common case is a backlog in one service.
- **Unlimited `per_repo`.** Worktree churn, disk pressure and provider limits turn parallelism into
  slower wall-clock time.
- **Preempting a run to start another.** Loses the guarantee that a started run finishes and its proof
  is bound to one uninterrupted attempt.
- **A distributed queue.** The product is one machine and one home (ADR 016); a local pool is enough.
