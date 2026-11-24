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
404 missing, 409 state/conflict, 502 harness, 503 unavailable, 500 unexpected.

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
| GET/DELETE | `/jobs/{id}` | status / cancel |
| POST | `/readiness` | 202 + job |
| POST | `/sources` | 202 + job |
| GET/POST | `/settings/builder` | builder health / save |
| GET | `/products`, `/detectors` | maps |
| GET | `/metrics`, `/ledger` | factory observability |
| GET | `/events` | SSE |
| POST | `/ask/stream` | SSE `delta`/`done`/`error` |

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
