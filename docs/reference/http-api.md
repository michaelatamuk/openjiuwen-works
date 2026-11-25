# Local HTTP API

The daemon serves `/api/v1` on loopback. The OpenAPI schema is
[`openapi.json`](openapi.json); the TypeScript client is generated from it.

## Auth

- Reads are open on loopback.
- Writes need the persistent bearer token from `.works/state/http-token`, or a session cookie
  created by `POST /api/v1/session` from a one-time bootstrap token.
- `Host` and `Origin` are checked; foreign values get `403`.
- A read-only daemon returns `403 read_only` for writes.

## Errors

`{ "ok": false, "error": { "code": "...", "message": "..." } }`

Statuses follow the `WorksError` class: 400 config/validation, 401 auth, 403 policy/read-only,
404 missing, 409 state/conflict, 413 body too large, 502 harness, 503 unavailable, 500 unexpected.
A `503` from job backpressure carries `Retry-After: 5`; retry the same request with the same
`Idempotency-Key`. A request may carry `X-Request-ID`; the response echoes it and the value is in the
request log.
Writes larger than 4 MiB are refused (declared or chunked); `WORKS_MAX_BODY_BYTES` overrides it.
`WORKS_MAX_PENDING_JOBS` (default 64) bounds queued jobs. Delivery semantics, crash reconciliation
and the no-auto-resume rule are in `docs/reference/reliability.md`.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | version, write mode, builder health |
| POST | `/session` | exchange a bootstrap/bearer token for an HttpOnly cookie |
| GET | `/tasks` | list, `?limit=` |
| POST | `/tasks` | create a task (201 new, 200 duplicate) |
| GET | `/tasks/{id}` | full detail |
| GET | `/tasks/{id}/runs` | run summaries |
| GET | `/tasks/{id}/export/{kind}` | attachment download |
| GET | `/tasks/{id}/artifacts/{name:path}` | inline artifact |
| POST | `/actions` | sync or 202 + job (see below) |
| POST | `/runs` | 202 + job; run one task through the saved builder or a trace |
| POST | `/dispatch` | 202 + job; run up to `limit` queued tasks |
| GET | `/runs/{run_id}` | a run record from disk |
| GET/DELETE | `/jobs/{id}` | status / cancel |
| POST | `/readiness` | 202 + job |
| POST | `/sources` | 202 + job |
| GET/POST | `/settings/builder` | builder health / save |
| GET | `/products`, `/detectors` | maps |
| GET | `/metrics`, `/ledger` | factory observability |
| GET | `/events` | SSE |
| POST | `/ask/stream` | SSE `delta`/`done`/`error` |
| POST | `/admin/shutdown` | authenticated graceful stop; not in the schema |
| POST | `/admin/rotate-token` | authenticated bearer-token rotation; clears sessions |

## Actions

Sync: `add-context`, `approve-plan`, `release`. Jobs: `commentary`, `discussion`, `deliver`,
`confirm`, `team-verify`, `deploy`. `ask` is refused here; use `/ask/stream`.

## Live events

`GET /events` sends named events with `id` and JSON `data`:

- `queue.changed`
- `task.changed` `{task_id}`
- `run.changed` `{task_id, run_id}`
- `job.changed` `{job_id, status}`
- `settings.changed`
- `heartbeat` every 15 s
- `resync` when `Last-Event-ID` falls outside the replay ring

The server keeps the last 200 events per process; a restart starts a new epoch.

## Daemon lifecycle

`works daemon` runs in the foreground. `works daemon start|stop|status` manages a detached
process, and `works ui` is the same app with the SPA at `/`.

- `.works/state/daemon.json` holds `{pid, host, port, home, started_at, token_path}`. A stale
  file is cleared when the pid is gone, the home does not match, or `/health` does not answer
  with this home's `root`. The pid is the daemon's own `os.getpid()`, announced after Uvicorn
  starts, because the Windows venv `python.exe` is a launcher and `Popen.pid` is not the server.
- A writable daemon takes an exclusive `.works/state/daemon.lock`; a second writable daemon for
  the same home refuses to start. Read-only daemons take no lock.
- The detached child runs with `cwd` set to the home, a small allow-listed environment, and
  output appended to `.works/state/daemon.log`.
- `works daemon stop` posts `/admin/shutdown` with the bearer token, falling back to
  `SIGTERM`/`CTRL_BREAK_EVENT`. It only kills a pid that still answers with this home's health
  identity, so a reused pid is never terminated.
- `works run --daemon` and `works dispatch --daemon` submit a job, wait for it, print the same
  JSON as the standalone commands, and return the same exit codes. Standalone runs refuse while
  a writable daemon owns the home. Relative scenario, quarantine, trace and prompt paths are
  resolved by the CLI before they are sent.
- A job may set `WORKS_JOB_TIMEOUT` (seconds). A timeout fails the job with `error_code: timeout`;
  cancelling a job kills its child process tree and no late result can overwrite the final status.
- Request logs and Uvicorn startup logs share the JSON formatter. Each request carries a
  `request_id`; jobs carry a `job_id`. Uvicorn access logging is disabled in favour of the request
  log.

`python scripts/smoke_daemon.py` is the lifecycle gate: it seeds a home, runs a read-only UI on a
second port, dispatches while stopping the UI, runs `works run --daemon`, kills the daemon
mid-run, checks restart reconciliation, and stops gracefully.


## Route classes

Every operation is classified in `src/works/interfaces/api/route_classes.py`; CI fails when a new route
is unclassified or this table is stale. A `blocking` route stays a sync function in the thread pool by
design (M10): only a measured hot read path moves to `async def`.

<!-- route-classes:start -->
| Method | Path | Class | Note |
|---|---|---|---|
| POST | `/api/v1/actions` | blocking | short calls answer inline; long ones are submitted as jobs |
| GET | `/api/v1/admin/devices` | blocking | reads the device file |
| DELETE | `/api/v1/admin/devices/{device_id}` | blocking | rewrites the device list and audits |
| POST | `/api/v1/admin/pair` | blocking | writes the device list and the audit log |
| POST | `/api/v1/admin/rotate-token` | blocking | rewrites the token file and audits |
| POST | `/api/v1/admin/shutdown` | blocking | asks the server to stop after the response |
| POST | `/api/v1/ask/stream` | sse | streams model tokens; a job owns the work |
| GET | `/api/v1/detectors` | blocking | reads the detector catalogue |
| POST | `/api/v1/dispatch` | blocking | selects queued tasks and submits run jobs |
| GET | `/api/v1/events` | sse | server-sent task events with a subscriber cap |
| GET | `/api/v1/health` | blocking | kept for compatibility; builder/provider diagnostics |
| GET | `/api/v1/health/live` | async-safe | no file or model access; cheap liveness |
| GET | `/api/v1/health/ready` | blocking | probes builder and provider readiness |
| POST | `/api/v1/hooks/{source}` | blocking | verifies HMAC, writes the task, the audit line and the metrics |
| GET | `/api/v1/inbox` | blocking | reads tasks and groups possible duplicates |
| POST | `/api/v1/inbox/mute` | blocking | rewrites the source registry |
| DELETE | `/api/v1/jobs/{job_id}` | async-safe | sets the in-memory cancel flag |
| GET | `/api/v1/jobs/{job_id}` | async-safe | reads the in-memory job record |
| GET | `/api/v1/ledger` | blocking | reads the append-only ledger |
| GET | `/api/v1/metrics` | blocking | reads job and queue counters |
| GET | `/api/v1/ops/metrics` | blocking | reads jobs, SSE subscribers and disk counters |
| POST | `/api/v1/pair` | blocking | mints a device token and writes the audit log |
| GET | `/api/v1/products` | blocking | reads the product map |
| POST | `/api/v1/readiness` | blocking | submits a readiness job; the job runs the commands |
| POST | `/api/v1/runs` | blocking | submits a run job; the supervisor spawns subprocesses |
| GET | `/api/v1/runs/{run_id}` | blocking | reads the run record and evidence |
| POST | `/api/v1/session` | async-safe | compares a token against in-memory sessions |
| GET | `/api/v1/settings/builder` | blocking | reads the builder settings file |
| POST | `/api/v1/settings/builder` | blocking | writes the builder settings file |
| GET | `/api/v1/sources` | blocking | reads the source registry and its metrics |
| POST | `/api/v1/sources` | blocking | submits an import job; the job calls the forge API |
| GET | `/api/v1/tasks` | async-safe | index page ids then hydrated summaries; no full scan |
| POST | `/api/v1/tasks` | blocking | writes a task and its event |
| GET | `/api/v1/tasks/{task_id}` | blocking | reads events, runs and artifacts |
| GET | `/api/v1/tasks/{task_id}/artifacts/{name:path}` | blocking | streams a file from the run dir |
| GET | `/api/v1/tasks/{task_id}/export/{kind}` | blocking | builds and streams an export |
| POST | `/api/v1/tasks/{task_id}/merge` | blocking | records the merge event and transitions the duplicate |
| GET | `/api/v1/tasks/{task_id}/runs` | blocking | reads run summaries |
<!-- route-classes:end -->

## Compatibility

`/api/v1` is additive-only. A field may be added at any time; removing or renaming one needs a
deprecation window and a schema change in the committed `openapi.json`. Generated clients are
checked against the committed schema in CI.
