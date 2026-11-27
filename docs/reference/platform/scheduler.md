# Scheduler (first pass)

Status: core implemented (policy, selection, leases, pause), the HTTP surface (status, pause, resume,
one tick as a job), a daemon loop for a writable daemon, and `dispatch_on_import` on task creation.
Bounded retries, `/sources` triggers and the remaining GUI parity are still planned.

The scheduler decides **whether** a queued task may run and **whether it should run now**. It never
runs a task itself and never decides a gate.

## Off by default

`<home>/config/dispatch.yaml` is the only policy. A missing file means "disabled", never "run
everything". `works scheduler enable` writes `enabled: true` and keeps the rest of the file.

```yaml
enabled: false
tick_seconds: 10
levels:
  default: L1
allow:
  sources: [github, jira, detector]
  labels: ["works:auto"]
  labels_deny: ["works:hold"]
  manual: false
concurrency:
  global: 2
  per_repo: 1
budget:
  daily_usd: 20        # overrides WORKS_DAILY_USD when set
  per_run_usd: 5
queue:
  max_age_hours: 72
  max_attempts: 2
  starvation_boost_hours: 24
windows:
  blackout: ["02:00-02:30"]
```

Unknown keys, a bad level or a bad window is a `config_error` at load.

## Commands

```bash
works scheduler status            # policy, slots, budget, eligible, waiting reasons
works scheduler status --json
works scheduler enable | disable
works scheduler pause --reason "deploying"
works scheduler resume
works scheduler tick --no-run     # plan only; claim nothing
works scheduler tick --live       # claim and run the selected task(s) sequentially
works dispatch --watch            # the same loop, foreground, for a headless machine
```

Exit codes: `0` on success, `EXIT_BLOCKED` when an executed task returns an error.

## HTTP

| method | path | meaning |
|---|---|---|
| GET | `/api/v1/scheduler` | state, slots, budget, eligible tasks, waiting reasons and job counters |
| POST | `/api/v1/scheduler/pause` | `{"reason": "..."}`; the queue is kept |
| POST | `/api/v1/scheduler/resume` | resume claiming |
| POST | `/api/v1/scheduler/tick` | submit a job that selects and runs sequentially; answers `202` |

Writes need the local bearer token; loopback reads follow the usual auth rules.

## In the daemon

Each tick writes `state/dispatcher.json` with the owner and the timestamp, so a status call can show
who is dispatching. A second dispatcher gets `conflict` with that owner. Meaningful ticks, pause,
resume, conflicts and errors are appended to `state/scheduler-events.jsonl`, and every claim writes a
zero-cost ledger row with `note: scheduler claim L1|L2|L3`.

A **writable** daemon starts the loop automatically: every `tick_seconds` it reloads the policy, and
when the policy is enabled it claims tasks and submits each claim as the same run job the manual path
uses. The lease is released when the job ends or when submission is refused. A broken policy or a
failing tick is logged and the loop continues.

## In the UI

Settings has a **Scheduler** card: state, tick interval, budget left, the next eligible tasks and the
waiting reasons, with Pause/Resume and **Tick now**. The queue header shows **Dispatch ready (N)** when
the scheduler is enabled and not paused; it submits one tick (limit 2) as a job. The Story card has a
**Run** button for a queued, reproduced or plan-approved task; it starts the same run job as
`works run`, outside the scheduler's selection.

## Triggers

`POST /api/v1/tasks` accepts `dispatch_on_import: true`. It validates the policy and, when allowed,
appends `scheduler.requested` to the new task; the next tick still decides. A refusal is **soft**: the
task is created and the response carries `scheduler: {"requested": false, "reason": ...}` with a typed
reason (`disabled`, `remote_trigger`, `manual_not_allowed`, `not_allowlisted`, `flow_not_allowed`,
`budget_exhausted`).

`POST /api/v1/sources` takes the same flag and records one result per created task. A client that is
not on loopback is treated as remote and refused unless the policy sets
`allow.remote_triggers: true`.

## Leases and slots

- The scheduler writes `queue/<task>/scheduler-lease.json` with a TTL. It does **not** use
  `queue/<task>/owner`: the supervisor claims that with the run id.
- `reclaim_stale` removes an expired lease and appends `scheduler.reclaimed`.
- One dispatcher per home: `state/dispatcher.lock`. A second tick in another process reports `busy`
  and claims nothing.
- `global` and `per_repo` slots are counted from active leases. `per_repo` is a count, not a
  switch: `2` lets two tasks in one repository run in parallel, each in its own worktree. The default
  is `1`; 1–3 is the recommended range, and `global` should not exceed the job pool (sized at startup
  from `global`, clamped to 2–8).
- A tick reserves the remaining budget claim by claim: each claim subtracts its `p90_usd`, so the same
  dollars are never promised twice.

## Why a task waits

Every refusal has a typed code, visible in `status` and `tick`:

`disabled`, `paused`, `not_runnable`, `not_allowlisted`, `missing_label`, `denied_label`,
`manual_not_allowed`, `flow_not_allowed`, `stale`, `waiting_on_event`, `attempts_exhausted`,
`backoff`, `risk_too_high`, `stale_approval`, `repo_busy`, `global_busy`, `budget_exhausted`,
`run_budget_cap`, `system_busy`, `interactive_load`, `low_disk`, `provider_degraded`,
`attention_full`, `blackout`, `terminal_failure`, `owned`. A reason is written to the task as
`scheduler.skipped` **when it changes**, not on every tick. A failed execution is retried only for
transient codes (`harness_error`, `internal_error`, `timeout`, `network_error`); a config error or a
policy failure records `retryable: false` and the task waits for a person as `terminal_failure`.

`stale_approval` is emitted when a plan approval expired or no longer matches the latest plan hash;
release approvals are checked for expiry (the release hash check lands with M21.5). `remote_trigger`
still waits for the import path (M21.7).

## Merging duplicates

```bash
works task <duplicate> --merge-into <target>
```

It records `task.merged` and blocks the duplicate, locally or through the daemon; the target must not
be terminal. History is never deleted.

## Estimates

`estimates.source` chooses the estimator:

- `history` (default) groups stored `evidence.json` by `flow` and `risk` and uses empirical p50/p90
  once a group has `min_samples` runs;
- `knn` compares the new job with similar past jobs (BM25 over titles, plus label and path overlap)
  and takes the neighbour quantiles, with the sample count recorded;
- `plan` uses the planner's `estimated_minutes`/`estimated_usd` for a task with a saved plan, then
  the grouped plan prior;
- `static` uses the per-flow prior.

A saved plan always supplies the estimate for that task (widened for the tail). The estimate is used
for the budget fit, the per-run cap and the size bucket; it is never shown as a deadline.

```bash
works estimate backtest            # coverage, pinball, tail misses, per group
works estimate backtest --json
works estimate promotion            # is a learned order ready?
works estimate promote --by anna --device laptop
```

The backtest exits non-zero when there are enough samples and p90 coverage is outside 85%..95%
(too narrow misses the tail; too wide hides the point). Promotion requires at least 50 shadow
claims, at least four weeks, agreement >= 80% and calibration inside the band; `learned` refuses to
load without that record. The person is recorded by name and device. When
history is thin, the planner's `plan_estimated_minutes`/`usd` fill the gap with `source: plan`.

`order.mode: shadow` computes a k-NN order over similar tickets and writes `scheduler.shadow` with
`rule` and `would` when the two differ; it claims nothing differently. `learned` uses the k-NN order
for claims, but only after `works estimate promote` records the evidence.

## Order

1. starvation (waited past `starvation_boost_hours`) — its own leading bucket;
2. risk (severity S1→critical … S4→low);
3. budget fragility (p90 estimate above half the remaining daily budget);
4. size bucket (small first);
5. age, oldest first;
6. task id, so the order is total and reproducible.

The claimed order and the estimate are written to the task history as `scheduler.claimed`.

## What is deliberately absent

- no approval of a plan or a release, at any level;
- no preemption of a started run;
- no parallel runs in one repository;
- no automatic merge, deploy or close;
- estimates are static per flow until M22.

## Related

- `docs/roadmap/milestones/m21-scheduler.md` — full design.
- `docs/adrs/024-scheduler-actor.md` — why the scheduler runs but never decides.
- `docs/adrs/025-ordering-cost-model.md` — why the order is a cost model, not a learned ranker.
