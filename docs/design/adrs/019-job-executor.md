# 019 - One bounded thread pool for jobs

**Status:** accepted  
**Date:** 2026-11-25

## Context

The [engineering standard](../engineering-standard.md) says "no bare threads".
`JobRunner` needs to run blocking work: git, subprocesses, file
writes to the queue and evidence. FastAPI already runs `def` routes in its own bounded thread pool, so
a second, ad-hoc pool would double the concurrency and hide the bound.

The 2026 plan (M10.3) forbids leaving the contradiction: either move to structured `asyncio` tasks or
record an explicit exception.

## Decision

Keep **one** bounded `ThreadPoolExecutor` owned by `JobRunner`, and treat it as the documented
exception to §6.4:

- `max_workers=2` by default; work is queue-bound, not CPU-bound.
- A bounded pending queue (`WORKS_MAX_PENDING_JOBS`, default 64) rejects new work with `503` and
  `Retry-After` instead of growing memory (`tests/unit/interfaces/api/test_jobs.py`).
- Threads are created once, named (`works-job`), and shut down with the runner. No module creates
  threads of its own.
- Cancellation is a `threading.Event` plus a process-tree kill; timeouts use a single `threading.Timer`
  per job; the heartbeat loop is one daemon thread that stops with the runner.
- Job state stays in JSON files written through `atomic_write`, so a crash is visible on restart
  (see `docs/reference/platform/reliability.md`).

Why not structured `asyncio` tasks: the bodies call synchronous SDKs and `subprocess`, so an async
executor would immediately hand them to `anyio.to_thread` — the same pool with an extra layer. Windows
process cancellation (`taskkill /T`) and the SDKs' blocking calls stay honest in a thread. Per-job
event loops would also complicate the existing `CURRENT_CANCEL` context variable.

## Consequences

- §6.4 is amended to "no **unbounded** or anonymous threads"; a new thread outside this pool needs a
  new ADR.
- The bound is observable: `/api/v1/metrics` reports queued/running counts and the 503 path has a test.
- If a future provider exposes a genuinely async API, a separate executor can be added behind the same
  queue without changing the HTTP surface.
