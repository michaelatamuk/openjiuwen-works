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

Every checkbox names the artifact it produces. A phase ends with a **gate**: a command (or a short
list) that must be green before the next phase starts. A box without a test is a review item, not
a done item.

### Phase 0 — preparation (0.5 day)

- [ ] `docs/adrs/016-local-daemon-and-typed-client.md`: decision, context, consequences; add it to
  `docs/adrs/README.md`. Verify: file linked from the ADR index.
- [ ] `scripts/capture_api_fixtures.py`: calls the legacy server on a demo home and writes every
  GET/POST response to `tests/contract/fixtures/*.json`. Verify: `uv run python scripts/capture_api_fixtures.py --check`
  exits 0 against current code.
- [ ] `tests/contract/test_baseline.py`: asserts the fixtures are present and have the expected
  top-level keys. Verify: `uv run pytest tests/contract -q`.
- [ ] CI smoke step in `.github/workflows/ci.yml`: `uv run works --help` and `uv run works version`.
  Verify: the `check` job is green on a branch.

**Gate:** `uv run pytest tests/contract -q` and the console smoke both pass.

### Phase 1 — daemon skeleton (1 day)

- [ ] `pyproject.toml`: extra `server = ["fastapi", "uvicorn", "sse-starlette"]`, dev extra gains
  `httpx`. Verify: `uv lock` updates and `uv sync --extra dev --extra server` succeeds.
- [ ] `src/works/interfaces/http/app.py`: `create_app(paths)` + lifespan that builds the queue and
  supervisor once. Verify: app imports and starts under Uvicorn.
- [ ] `src/works/interfaces/http/wiring.py`: one dependency builder used by tests and the daemon.
  Verify: no second copy of `WorksPaths`/`Queue` construction.
- [ ] `src/works/interfaces/http/routes/health.py`: `GET /api/v1/health` with the exact legacy keys
  (`ok`, `readonly`, `write`, `root`, `version`, `ai`, `builder`). Verify: schema test below.
- [ ] `src/works/interfaces/cli/commands/daemon.py`: `works daemon --host --port --write`; registered
  in `cli/parser/run.py`.
- [ ] `tests/unit/interfaces/http/test_health.py`: `httpx.ASGITransport`, asserts keys and values.
  Verify: `uv run pytest tests/unit/interfaces/http -q`.

**Gate:** `uv run pytest tests/unit/interfaces/http -q` and `uv run works daemon --help`.

### Phase 2 — read API (2 days)

- [ ] `src/works/interfaces/http/schemas/tasks.py`: `TaskSummary`, `TaskDetail`, `RunSummary`,
  `Pipeline`, `ThreadMessage`, `Rail`, `ArtifactDownload`. Verify: models import and round-trip
  fixtures via `model_validate`.
- [ ] `src/works/interfaces/http/routes/tasks.py`: `GET /tasks`, `/tasks/{id}`, `/tasks/{id}/runs`.
  Verify: contract test `tests/contract/test_tasks_api.py`.
- [ ] `src/works/interfaces/http/routes/maps.py`: `/products`, `/detectors`. Verify: contract tests.
- [ ] `src/works/interfaces/http/routes/observability.py`: `/metrics`, `/ledger`. Verify: contract
  tests.
- [ ] `src/works/interfaces/http/routes/downloads.py`: exports and artifacts via `FileResponse`,
  path confined to the run directory. Verify: traversal test (below) and contract test.
- [ ] `tests/contract/test_read_api.py`: for each fixture, start the new app on an empty home, seed
  the same data, and assert JSON equality (field order irrelevant, timestamps normalized).
- [ ] `tests/unit/interfaces/http/test_downloads.py`: rejects `../`, absolute paths, and a missing
  run; serves a real artifact with the right content type.

**Gate:** `uv run pytest tests/contract tests/unit/interfaces/http -q` (all read endpoints).

### Phase 3 — write API (2 days)

- [ ] `src/works/interfaces/http/security.py`: token file `.works/state/http-token` (owner-only),
  `POST /api/v1/session` cookie bootstrap, loopback `Host` check. Verify:
  `tests/unit/interfaces/http/test_security.py` covers missing token, wrong token, bad Host.
- [ ] `src/works/interfaces/http/jobs.py`: executor with `max_workers=2`, statuses, cancellation,
  log tail. Verify: `tests/unit/interfaces/http/test_jobs.py` with a fake long job and a cancel.
- [ ] `src/works/interfaces/http/routes/actions.py`: all eight actions; `ask`, `team-verify`,
  `readiness`, `deliver`, `confirm` return 202 + job. Verify: `tests/contract/test_actions_api.py`
  plus a job-status test.
- [ ] `routes/tasks.py`: `POST /tasks` with `Idempotency-Key`; replay returns the first result.
  Verify: a test that posts twice and asserts one task.
- [ ] `routes/sources.py`, `routes/settings.py`, `routes/readiness.py`.
- [ ] `app.py`: one exception handler implementing the status mapping from §5.2. Verify: a
  parametrized test per `WorksError` subclass.
- [ ] `scripts/smoke_api.py`: create → approve-plan → release → confirm against a demo home.

**Gate:** `uv run pytest tests/unit/interfaces/http tests/contract -q` and `uv run python scripts/smoke_api.py`.

### Phase 4 — live updates (1 day)

- [ ] `src/works/interfaces/http/live.py`: broadcaster task draining `LiveState`, a ring buffer of
  the last 200 events for `Last-Event-ID`, 15 s heartbeat.
- [ ] `routes/events.py`: `StreamingResponse` with `text/event-stream`, disconnect handling.
  Verify: `tests/unit/interfaces/http/test_sse.py` asserts event names, ids, heartbeat and replay.
- [ ] `routes/ask.py`: `POST /ask/stream` with the existing `delta`/`done`/`error` payloads.
  Verify: mocked worker streaming test.
- [ ] `docs/reference/http-api.md`: one page with the endpoints, events and error codes.

**Gate:** `uv run pytest tests/unit/interfaces/http/test_sse.py -q`.

### Phase 5 — TypeScript frontend (3–4 days)

- [ ] `web/package.json`: add `typescript`, `@tanstack/react-query`, `zustand`, `zod`,
  `openapi-typescript`, `vitest`; scripts `dev`, `build`, `typecheck`, `test`, `generate:api`.
  Verify: `npm ci && npm run typecheck`.
- [ ] `web/tsconfig.json`: `strict`, `allowJs`, `jsx: react-jsx`; new files are `.ts`/`.tsx`.
- [ ] `web/src/api/generated/schema.d.ts`: generated from `/api/v1/openapi.json`; committed.
  Verify: CI regenerates and fails on `git diff --exit-code`.
- [ ] `web/src/api/client.ts`: fetch wrapper with credentials, typed errors, `Idempotency-Key`.
- [ ] `web/src/api/hooks.ts`: `useTasks`, `useTaskDetail`, `useActions`, `useJob`, `useMetrics`.
  Verify: `vitest` tests with a mocked fetch.
- [ ] `web/src/api/useEvents.ts`: SSE with reconnect and cache invalidation.
- [ ] Screens migrated one by one, each with its parity items from §18: Queue, Story, Evidence,
  Release, Session, Settings, dialogs, palette/help.
- [ ] Delete `web/src/lib/api.js` and the last `EventSource` call site.

**Gate:** `npm run typecheck && npm test && npm run build`, plus a manual parity pass through §18.

### Phase 6 — process split (2 days)

- [ ] `works daemon start|stop|status`: pidfile `.works/state/daemon.pid`, log
  `.works/state/daemon.log`, single-instance lock. Verify: start twice → second exits with a clear
  message; stale pidfile is recovered.
- [ ] CLI transport: `--standalone` (default for one-shot) and `--daemon` (HTTP + token).
  Verify: the same command returns the same JSON in both modes.
- [ ] `works ui`: start the daemon if needed, wait for `/health`, open the browser.
- [ ] Static mount: `dist` at `/`, SPA fallback to `index.html`, no legacy `/app.js`.
- [ ] `dispatch --watch` refuses to run when the daemon owns the queue (or requires
  `--standalone`).

**Gate:** daemon + UI + a queued dispatch run at the same time; no lock conflicts; killing the UI
does not stop the run.

### Phase 7 — cutover (1 day)

- [ ] Delete `interfaces/api/{server,read,write,downloads,static}.py`; update imports.
  Verify: `uv run ruff check src tests` and `uv run mypy`.
- [ ] `pyproject.toml`: `server` extra required by `works ui`; wheel content test
  `tests/test_packaging.py` asserts `interfaces/ui/static/dist/index.html` is in the wheel.
- [ ] `.github/workflows/ci.yml`: add `web` (node 22, `npm ci`, typecheck, build) and `contract`
  jobs; keep `check`, `docker-verifier`, `benchmark`, `security`.
- [ ] Docs: `docs/guides/ui.md`, `docs/guides/runbook.md`, `docs/reference/layout.md`,
  `README.md` commands.
- [ ] Tag `pre-fastapi` before the deletion commit.

**Gate:** CI green on the cutover commit; `uv build` wheel contains `dist`.

### Phase 8 — hardening (2 days)

- [ ] `scripts/load_api.py`: 200 tasks, 20 parallel SSE clients, p95 recorded. Targets from §13.
- [ ] Timeout and cancel tests: a slow action is cancelled and the job records `cancelled`.
- [ ] Security tests: bad Host/Origin/token, oversized body, path traversal, duplicated
  `Idempotency-Key`.
- [ ] Metrics wired: request latency, queue depth, active runs, job failures, SSE clients.
- [ ] Final runs: `pytest`, `ruff`, `mypy`, `tsc --noEmit`, `vite build`, docker verifier.
- [ ] ADR-016 updated with the final decisions from §19.

**Gate:** every check in §17 passes on a fresh clone.

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
