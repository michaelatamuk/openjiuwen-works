# Reliability, crashes and delivery semantics

One home is owned by one local daemon. State lives in files and JSONL, not in a database, so the
interesting question is not "did the transaction commit" but "what happens when the process dies
between two file writes".

This page states the guarantees the daemon actually provides today. Nothing here needs a cloud
service, a message broker or a second process.

## Delivery semantics

| Thing | Semantics | Where it is enforced |
|---|---|---|
| HTTP `POST` with side effects | at-most-once per `Idempotency-Key` | `interfaces/api/idempotency.py` |
| Job body (`deliver`, `confirm`, `deploy`, commentary, discussion, team-verify) | **at-least-once** | `interfaces/api/jobs.py` |
| Source intake | idempotent by `(kind, ref)` | `application/intake` |
| Tracker comment on delivery | idempotent by run marker | `application/delivery` |
| `POST /tasks` | deterministic: same payload, same task id | `routes/tasks.py` |
| `POST /pair` | deliberately **not** idempotent; it mints a one-time code | `interfaces/api/security.py` |

"At-least-once" means a job body may run again after a retry or an operator re-run. It does **not**
mean the daemon retries on its own after a crash: see the next section.

## What a crash does

A daemon writes each job to `state/jobs/<job-id>.json` through `atomic_write`, so a truncated file is
never visible. On startup `JobRunner.reconcile()`:

1. loads every job file, skipping unreadable or incompatible payloads;
2. marks any `queued` or `running` job as `failed` with
   `"daemon restarted while the job was running"`;
3. sets `finished_at`, clears `cancelable`;
4. releases the queue owner for the job's `task_id`, if any.

A killed run is therefore **terminal and visible**, never silently "still running".

### No auto-resume

Killed jobs are not restarted automatically. A run may have half-written a worktree, created a
branch, opened a pull request or started a deploy; resuming from the last recorded phase would
repeat exactly the external action that is hardest to undo. The operator decides:

```powershell
works status                       # what the daemon thinks is true
works inspect <job-id>             # last error and log tail
works run <task-id> ...            # an explicit, fresh attempt
```

`works doctor --bundle out.tar.gz` collects the job summaries, daemon identity, index health, disk
usage and log tails (no tokens) for a bug report.

### Child processes

On Windows every command is assigned to a Job Object with `KILL_ON_JOB_CLOSE`: killing Works hard
closes the handle and the whole process tree dies with it. On Linux the child asks the kernel for
`PR_SET_PDEATHSIG` (`SIGKILL`), so it dies with the daemon even when the daemon itself is `SIGKILLed`
(`tests/unit/adapters/processes/test_orphan.py`). On macOS there is no equivalent; a hard kill of the
daemon can leave a command running, which is the remaining gap in this section.

## Phase idempotency

Read-only or file-local phases are safe to repeat. Phases that touch the outside world are only safe
when their own key or marker exists.

| Phase | Safe to repeat? | Why |
|---|---|---|
| `reproduce`, `check`, `proof` | yes | read the repo and write run artifacts under a new run id |
| `plan` | yes | a new plan version is written and hashed |
| `build` | yes | works in a fresh worktree |
| `deliver` | only with a delivery marker | the marker makes a repeat a no-op instead of a second PR/comment |
| `deploy` | only with an explicit `--force` after a crash | a `running` record is written before the command, so an interrupted deploy is refused instead of silently repeated |
| `confirm` | yes | it only observes the target and writes a new confirmation record |

## Heartbeats

Each job records `daemon_id`, `pid` and `heartbeat_at`. While a job is `queued` or `running` a
daemon thread refreshes `heartbeat_at` every 5 seconds and rewrites the job file. A stale heartbeat
on a live daemon means a blocked body; a stale heartbeat after a restart is expected and the job is
already failed by `reconcile()`.

Heartbeats are diagnostics. They never cause an automatic kill or an automatic retry; the per-job
`timeout_s` timer is the only automatic termination path.

## Backpressure

* `WORKS_MAX_PENDING_JOBS` (default `64`) bounds queued jobs. Past the limit `submit()` raises
  `UnavailableError`, the API answers `503` and sends `Retry-After: 5`.
* Two concurrent jobs on the same task are rejected with `409` instead of racing on the queue.
* `/api/v1/live` caps SSE subscribers and drops slow consumers rather than growing an unbounded
  buffer.

The client contract is therefore: on `503` wait for `Retry-After` and retry the same request with the
same `Idempotency-Key`; on `409` re-read the task and do not retry blindly.

## Budgets

Two ceilings, both typed as `budget_exceeded` and both ending in a visible `blocked` state:

* **Per run** — `Task.budget` (`tokens`, `usd`, `wall_minutes`) is checked after the builder turn
  and against the wall clock; a run over budget stops instead of continuing quietly.
* **Per day** — `WORKS_DAILY_USD` caps the sum of today's `usd` in the append-only ledger. It is
  checked before the run starts and again before the verifier spends money; an over-budget start
  still writes a blocked run record with zero tokens, so the operator sees why nothing happened.
  Unset means no daily ceiling. The day boundary is UTC.

## Retention and recovery

* `works prune-jobs --days 30 [--dry-run] [--json]` appends one summary line per pruned terminal job
  to `state/jobs-archive.jsonl` and deletes the job file. Non-terminal jobs are never pruned.
* `works backup <file>` archives events, runs, ledger and settings without credentials or disposable
  worktrees; `works restore <file>` restores them.
* The task index rebuilds from events and has a time budget; a corrupt or old index is rebuilt rather
  than trusted.

## Tracing

Instrumentation is always on but the OpenTelemetry API is a **no-op unless asked**: a plain daemon
creates spans that go nowhere, which cost 0.3% on the p95 benchmark (78.45 -> 78.68 ms on 10k tasks
with 20 SSE streams).

```bash
WORKS_OTEL=1 works daemon start ...                  # spans to the daemon log
WORKS_OTEL=1 WORKS_OTEL_ENDPOINT=http://host:4318/v1/traces works daemon start ...   # OTLP/HTTP
WORKS_OTEL=1 WORKS_OTEL_EXPORTER=none works daemon start ...   # instrument, drop spans
```

What is traced today:

- one span per HTTP request (`http GET /api/v1/tasks`) with the status code;
- one span per job body (`job.run`) with job id, action and task;
- one span per supervised subprocess.

The request trace id is written into the job record and the job logs (`trace_id`), so a job can be
followed from the browser request that started it. No collector is needed for a local trace: the
console exporter writes the finished span as one JSON line.

## See also

- `docs/design/adrs/016-local-daemon.md` - why one daemon owns one home.
- `docs/reference/platform/http-api.md` - status codes, idempotency and retry hints.
- `docs/guides/operations/runbook.md` - day-to-day operation.
