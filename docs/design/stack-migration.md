# Migrating to a separate backend and frontend

**Status:** plan (not started)
**Date:** 2026-11-24

## 1. Goal

Split the product into two processes and two independent codebases:

- **backend** — a local daemon in Python that owns the queue, runs, SSE and long actions;
- **frontend** — a React/TypeScript SPA, a thin client over a typed API.

The engine (`domain/`, `application/`, `adapters/`) is **not rewritten**. This plan wraps the
existing logic in a modern HTTP layer and a typed client.

## 2. Principles

1. The event log and run artifacts stay the source of truth.
2. One writer: the daemon owns the queue. The CLI either attaches to it or runs standalone.
3. The CLI stays a first-class interface, not a second-class client.
4. Local daemon, not cloud: localhost or a named pipe, with a token for writes.
5. No microservices, Redis, Postgres or GraphQL.
6. The API is versioned (`/api/v1`); the UI types are generated from OpenAPI.
7. The old stdlib server stays until the final cutover and is deleted at the end.

## 3. Target architecture

```
Browser
  └─ SPA (React/TS) ── HTTP/JSON + SSE ──┐
                                        │
CLI (works …) ── in-process ────────────┤
   └─ or HTTP client ───────────────────┤
                                        ▼
                             worksd (FastAPI/Uvicorn)
                             ├─ REST /api/v1
                             ├─ SSE /api/v1/events
                             ├─ queue and scheduler (asyncio)
                             ├─ long actions (jobs)
                             └─ application/ (existing engine)
                                        │
                             adapters: files, git, harness, docker
```

Production processes: **daemon + browser**. Development: **Uvicorn + Vite + browser**.

## 4. Stack

**Backend**
- **Python 3.13** (the project supports `>=3.12,<3.14`; move to 3.14 later, separately).
- FastAPI, Uvicorn, Pydantic v2, `sse-starlette`.
- asyncio tasks; `watchfiles` to watch the queue.
- SQLite (the existing index) and file locks — unchanged.
- `structlog`, optionally OpenTelemetry.
- Packaging: extra `server = [fastapi, uvicorn, sse-starlette]`.

**Frontend**
- React 19 + Vite + TypeScript.
- TanStack Query (server state), Zustand (local UI state).
- Tailwind v4 + shadcn/ui.
- Zod + `openapi-typescript` → `web/src/api/generated`.
- SSE hook instead of a hand-written `EventSource`.

## 5. Contracts

### 5.1 REST endpoints

Version `/api/v1`. Errors: `{ "ok": false, "error": { "code", "message" } }`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | version, write mode, builder |
| GET | `/products`, `/detectors` | product and detector maps |
| GET | `/tasks?limit=` | task list |
| POST | `/tasks` | create a task (201 created, 200 existing) |
| GET | `/tasks/{id}` | detail (story, proof, rail, runs) |
| GET | `/tasks/{id}/runs` | run summaries |
| GET | `/tasks/{id}/export/{kind}` | download a run artifact |
| GET | `/tasks/{id}/artifacts/{name}` | runtime artifact |
| POST | `/actions` | short actions return 200; long ones return 202 + job |
| GET | `/jobs/{id}`, `DELETE /jobs/{id}` | job status and cancellation |
| POST | `/readiness` | repository readiness (long → 202) |
| POST | `/sources` | import GitHub/Jira/detector |
| GET/POST | `/settings/builder` | builder/planner settings |
| GET | `/metrics`, `/ledger` | observability |
| GET | `/events` | SSE: queue, task, run and job updates |
| POST | `/ask/stream` | streamed Mira answer (SSE) |

Long actions: `ask`, `team-verify`, `readiness`, `deliver`, `confirm`. Everything else answers
synchronously. Success and error bodies keep today's field names.

### 5.2 Error and status mapping

`WorksError.code` is the API error code; status comes from the class:

| Error | Status |
|---|---|
| `ConfigError` / `ValueError` | 400 |
| `PolicyError` | 403 |
| `NotFoundError` | 404 |
| `StateError`, `ConflictError` | 409 |
| `HarnessError` | 502 |
| any other `WorksError` | 500 |
| unexpected exception | 500, logged with a request id |

Unknown routes return 404 with `{"ok": false, "error": {"code": "not_found"}}`. The old server
collapsed many of these into 404; the new API must not.

### 5.3 SSE events

`GET /api/v1/events` sends `id`, `event` and JSON `data`:

| Event | Data |
|---|---|
| `queue.changed` | `{}` |
| `task.changed` | `{"task_id": "t-…"}` |
| `run.changed` | `{"task_id": "t-…", "run_id": "r-…"}` |
| `job.changed` | `{"job_id": "j-…", "status": "running"}` |
| `heartbeat` | `{"ts": "…"}` every 15 s |

The `id` is a monotonic counter; clients send `Last-Event-ID` to resume. `ask/stream` keeps the
current `delta` / `done` / `error` events.

### 5.4 Auth and origin

- The daemon writes a random token to `.works/state/http-token` with owner-only permissions.
- `works ui` opens `http://127.0.0.1:<port>/?bootstrap=<one-time-token>`; the SPA calls
  `POST /api/v1/session` once, gets an HttpOnly `SameSite=Strict` cookie, and drops the URL token.
- Reads work without the cookie; every mutating request requires it (or `Authorization: Bearer` for
  the CLI).
- Bind to `127.0.0.1` only; reject requests whose `Host` is not a loopback name.
- No CORS in production. The Vite dev proxy makes the browser same-origin.

### 5.5 Jobs and idempotency

- Long actions run as jobs: `{id, action, status: queued|running|succeeded|failed, started_at,
  finished_at, result, error, log_tail}`.
- Max 2 concurrent jobs; extra ones queue. Cancellation kills the worker thread’s subprocess where
  possible and records `cancelled`.
- `POST /tasks` and `POST /actions` accept `Idempotency-Key`; a replay returns the first result.

## 6. Concurrency and the blocking engine

- Uvicorn runs **one worker**. One writer, one process, file locks unchanged.
- The engine is synchronous/blocking. Never call `Supervisor.run` on the event loop: run it in a
  dedicated thread (`asyncio.to_thread` or a small executor with its own `asyncio.run`).
- Long actions (Mira, team verify, readiness, deliver, confirm) use the same job executor.
- `LiveState` keeps its watcher thread and `queue.Queue`; one broadcaster task drains it and fans
  out to SSE clients, so clients never block each other.
- SSE writes use `StreamingResponse` with a per-client buffers and a disconnect check.
- `FileLock` stays for cross-process safety; `dispatch --watch` only runs inside the daemon.

## 7. File mapping

| Today | After |
|---|---|
| `interfaces/api/server.py` | `interfaces/http/app.py` + `routes/` (deleted) |
| `interfaces/api/read.py` | `interfaces/http/routes/tasks.py`, `observability.py` |
| `interfaces/api/write.py` | `interfaces/http/routes/actions.py`, `sources.py`, `settings.py` |
| `interfaces/api/downloads.py` | `interfaces/http/routes/downloads.py` (`FileResponse`) |
| `interfaces/api/static.py` | `StaticFiles` mount + an asset fallback route |
| `interfaces/api/live.py` | keep `LiveState`; add `http/live.py` SSE bridge |
| `interfaces/api/presenters/*` | keep; wrap with Pydantic response models |
| `interfaces/cli/commands/ui.py` | start/attach the daemon; `--legacy` while migrating |
| `web/src/lib/api.js` | `web/src/api/client.ts` (generated types) |
| `web/src/app/App.jsx` | shell; `EventSource` replaced by `useEvents` |

Delete at cutover: `server.py`, `read.py`, `write.py`, `downloads.py`, `static.py` gaps,
`web/src/lib/api.js`, and the legacy `/app.js` fallback.

## 8. Phases

### Phase 0 — preparation (0.5 day)
- [x] Fix the console script: `works = "works.interfaces.cli.main:main_entry"`.
- [ ] ADR-016 "local daemon and typed client".
- [ ] Freeze the current JSON as a baseline (record sample responses).
- [ ] CI smoke test for `works --help` and `works version`.

**Done when:** `works.exe` works and the contract is recorded.

### Phase 1 — daemon skeleton (1 day)
- [ ] `src/works/interfaces/http/app.py` — FastAPI plus lifespan.
- [ ] Dependency wiring: build `WorksPaths`, `Queue`, `Supervisor` and settings once.
- [ ] `GET /api/v1/health` with the same fields.
- [ ] `works daemon --host --port --write` command.
- [ ] `httpx.ASGITransport` for tests.

**Done when:** Uvicorn starts, health is green, the old UI still works.

### Phase 2 — read API (2 days)
- [ ] Pydantic response schemas in `interfaces/http/schemas/`.
- [ ] Move `presenters/` into response models: tasks, detail, story, thread, rail.
- [ ] products, detectors, metrics, ledger, runs, exports, artifacts.
- [ ] Contract tests: old JSON == new JSON (fixtures from Phase 0).

**Done when:** every GET endpoint matches the old contract.

### Phase 3 — write API (2 days)
- [ ] `POST /tasks`, `/actions`, `/readiness`, `/sources`, `/settings/builder`.
- [ ] Jobs for long actions; idempotency keys; token and origin checks.
- [ ] Error mapping table implemented once, in one handler.
- [ ] Shared locks: file locks stay, plus one job executor.

**Done when:** create/approve/release flows work through the new API.

### Phase 4 — live updates (1 day)
- [ ] `LiveState` → SSE broadcaster with a heartbeat and `Last-Event-ID`.
- [ ] `POST /ask/stream` as a FastAPI streaming response.
- [ ] Reconnect with backoff on the client.

**Done when:** an open tab updates without polling and survives a dropped stream.

### Phase 5 — TypeScript frontend (3–4 days)
- [ ] `tsconfig`, `strict: true`, optional ESLint, `vitest`.
- [ ] `openapi-typescript` → `web/src/api/generated/schema.d.ts`.
- [ ] Thin client `web/src/api/client.ts` (fetch plus cookie).
- [ ] TanStack Query hooks: `useTasks`, `useTaskDetail`, `useActions`, `useMetrics`, `useJob`.
- [ ] SSE hook `useEvents`.
- [ ] Migrate screens one by one: Queue → Story → Evidence → Release → Session → Settings.
- [ ] Delete `lib/api.js` after the move.

**Done when:** `tsc --noEmit` and `vite build` are green and the UI runs on the new API.

### Phase 6 — process split (2 days)
- [ ] `works daemon start|stop|status`, pidfile, port, log.
- [ ] CLI: `--standalone` (as today) and `--daemon` (HTTP).
- [ ] UI assets: the backend serves `dist` via `StaticFiles`.
- [ ] One writer: `dispatch --watch` runs only inside the daemon.
- [ ] `works ui` = start daemon if needed + open the browser.

**Done when:** UI and `dispatch` run together without races; closing the UI does not kill runs.

### Phase 7 — cutover (1 day)
- [ ] FastAPI is the only server; the stdlib server is deleted.
- [ ] `uvicorn` and `sse-starlette` are declared (extra `server`).
- [ ] CI: `tsc --noEmit`, contract tests, daemon smoke test.
- [ ] Docs: `docs/guides/ui.md`, `docs/reference/layout.md`, `docs/guides/runbook.md`.

**Done when:** CI is green, `works ui` starts the daemon, old code is gone.

### Phase 8 — hardening (2 days)
- [ ] Load smoke: 200 tasks, 20 parallel SSE clients.
- [ ] Errors: timeouts, request cancellation, retries.
- [ ] Security: token, Host/Origin checks, request size limits.
- [ ] Metrics: API latency, queue depth, active runs.
- [ ] Final full test run and ADR update.

## 9. Frontend migration mechanics

- Start with `allowJs: true`, `checkJs: false`; new files are `.ts`/`.tsx` with `strict`.
- Keep the current CSS and component structure; only state/data access changes.
- Vite dev proxy: `/api` → `http://127.0.0.1:8765`; production is same-origin.
- Query keys: `["tasks"]`, `["task", id]`, `["metrics"]`, `["job", id]`; invalidate on SSE and
  after every mutation; refetch the open task on `task.changed`.
- Map API error codes to the existing toast strings; keep the same user-visible wording.
- Generated types are committed; CI regenerates and fails on a diff.
- npm scripts: `dev`, `build`, `typecheck`, `test`, `generate:api`.

## 10. Structure after the migration

```
src/works/interfaces/http/
  app.py            # FastAPI, lifespan, wiring
  routes/           # tasks, actions, sources, settings, observability, downloads
  live.py           # SSE bridge and ask stream
  schemas/          # Pydantic request/response models
  security.py       # token, cookie, origin checks
  jobs.py           # executor, status, cancellation
web/src/
  api/              # client.ts, generated/, hooks (TanStack Query)
  app/              # shell, routing
  features/         # queue, story, evidence, release, session, settings
  ui/               # primitives
  styles/
```

## 11. Testing and CI

- Backend: pytest with `httpx` ASGI; contract tests compare old and new JSON fixtures; SSE tests
  with a fake clock; job tests for status and cancellation.
- Frontend: `tsc --noEmit`, `vitest` for hooks and pure helpers, `vite build`.
- E2E (optional): Playwright on demo data covering report → approve → release → confirm.
- CI jobs: `check` (unchanged), `web` (node 22, `npm ci`, typecheck, build), `contract`,
  `docker-verifier`, `benchmark`, `security`.
- Add one smoke step: `uv run works --help` and `uv run works version`.

## 12. Packaging and release

- Extra `server`; `works ui` explains how to install it if FastAPI is missing.
- Wheel includes `src/works/interfaces/ui/static/dist`; add a wheel-content test.
- Entry points stay `works`; `works daemon` is a subcommand, not a second script.
- OpenAPI at `/api/v1/openapi.json`; the interactive docs are off by default.
- Version the API path, not the package: `/api/v1` stays stable across releases.

## 13. Observability and targets

- Logs: JSON with `request_id`, `task_id`, `run_id`, `job_id`, `duration_ms`.
- Metrics: request latency, queue depth, active runs, job failures, SSE clients.
- Targets: p95 reads < 150 ms, p95 writes < 300 ms, SSE fan-out to 20 clients, memory < 300 MB.

## 14. Security

- Loopback bind, token-gated writes, `SameSite=Strict` cookie.
- Artifact paths resolved and confined to the run directory (already in `downloads.py`).
- Request body limit 64 KB on writes (as today).
- No secrets in the UI state; Mira answers stay advisory and are stored as events.

## 15. Risks

| Risk | Mitigation |
|---|---|
| Long actions block HTTP | job executor, `asyncio.to_thread`, limits |
| Double writes (UI + dispatch) | one daemon owns the queue; standalone CLI is manual only |
| Contract drift | contract tests on recorded fixtures |
| SSE through proxies/antivirus | heartbeat, reconnect, polling fallback |
| Windows paths and `claude.exe` | do not change adapter logic |
| Long UI migration | migrate screen by screen, keep routing compatible |
| Losing CLI simplicity | `--standalone` stays the default for one-shot runs |
| Python upgrade pressure | stay on 3.13 until 3.14 is explicitly supported |

## 16. Estimate

| Phase | Days |
|---|---|
| 0. Preparation | 0.5 |
| 1. Daemon skeleton | 1 |
| 2. Read API | 2 |
| 3. Write API | 2 |
| 4. Live | 1 |
| 5. TypeScript frontend | 3–4 |
| 6. Processes | 2 |
| 7. Cutover | 1 |
| 8. Hardening | 2 |
| **Total** | **~14–16 days** |

## 17. Definition of done

- [ ] `works ui` starts the daemon; the UI runs on `/api/v1`.
- [ ] CLI: both `--standalone` and `--daemon` work.
- [ ] Contract tests: old and new JSON match.
- [ ] `pytest`, `ruff`, `mypy`, `tsc --noEmit`, `vite build` are green.
- [ ] CI is green; the stdlib server is deleted.
- [ ] ADR-016 and updated guides are committed.

## 18. Parity checklist (must work in the new UI)

- Queue: search, filters (state/product/source), selection, live dot.
- New task: prompt draft, details, product/repo/ref/title, source and task kind, flow.
- Import: GitHub, Jira, detector; duplicate handling.
- Story: route, receipts, replay slider, present mode, copy link.
- Evidence: pipeline, verdict, findings, challenge, commands, change, readiness, features,
  artifacts/lightbox, timeline filters, exports.
- Release: packet, gate 2, deliver, deploy, confirm, compare runs.
- Session: transcript, chapters, ask/stream, review, commentary, add context, run log.
- Settings: builder runtime/provider, verifier split, planner modes/critic, theme/density/poll,
  repository path.
- Palette, help, toasts, theme persistence, keyboard shortcuts.

## 19. Open decisions

- Token delivery: cookie bootstrap (recommended) vs a meta tag injected into `index.html`.
- Keep `WORKS_HTTP=legacy` for one release, or cut over in a single change.
- `works daemon` vs a separate `worksd` entry point.
- Whether `GET /tasks/{id}` keeps one large payload or splits into `summary` + `thread`.
- TypeScript strictness ramp: per-file now, whole tree before cutover.

## 20. Rollback

- Before Phase 7: the old server stays; switch with `WORKS_HTTP=legacy`.
- After cutover: a `pre-fastapi` tag plus rollback instructions in the ADR.
