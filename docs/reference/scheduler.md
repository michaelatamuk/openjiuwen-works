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

A client that is not on loopback is treated as remote and refused unless the policy sets
`allow.remote_triggers: true`. The `/sources` import path does not take the flag yet; its tasks are
found by the periodic tick like any other.

## Leases and slots

- The scheduler writes `queue/<task>/scheduler-lease.json` with a TTL. It does **not** use
  `queue/<task>/owner`: the supervisor claims that with the run id.
- `reclaim_stale` removes an expired lease and appends `scheduler.reclaimed`.
- One dispatcher per home: `state/dispatcher.lock`. A second tick in another process reports `busy`
  and claims nothing.
- `global` and `per_repo` slots are counted from active leases.

## Why a task waits

Every refusal has a typed code, visible in `status` and `tick`:

`disabled`, `paused`, `not_runnable`, `not_allowlisted`, `missing_label`, `denied_label`,
`manual_not_allowed`, `flow_not_allowed`, `stale`, `waiting_on_event`, `attempts_exhausted`,
`backoff`, `risk_too_high`, `repo_busy`, `global_busy`, `budget_exhausted`, `run_budget_cap`,
`system_busy`, `interactive_load`, `low_disk`, `provider_degraded`, `attention_full`, `blackout`.

`stale_approval` is emitted when a plan approval expired or no longer matches the latest plan hash;
release approvals are checked for expiry (the release hash check lands with M21.5). `remote_trigger`
still waits for the import path (M21.7).

## Estimates

When the policy sets `estimates.source: history`, the scheduler groups stored `evidence.json` by
`flow` and `risk` and uses empirical p50/p90 minutes and dollars once a group has
`estimates.min_samples` runs (default 5). Otherwise it falls back to a static per-flow prior. The
estimate is used for the budget fit, the per-run cap and the size bucket; it is never shown as a
deadline.

```bash
works estimate backtest            # leave-one-out p90 coverage and pinball loss
works estimate backtest --json
```

The command exits non-zero when there are enough samples and p90 coverage falls below 80%.

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

- `docs/design/2026-m21-scheduler.md` — full design.
- `docs/adrs/024-scheduler-actor.md` — why the scheduler runs but never decides.
- `docs/adrs/025-ordering-cost-model.md` — why the order is a cost model, not a learned ranker.
