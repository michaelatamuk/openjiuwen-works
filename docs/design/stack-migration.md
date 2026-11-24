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
- Python 3.14, FastAPI, Uvicorn, Pydantic v2
- `sse-starlette` for the event stream (fallback: WebSocket)
- asyncio tasks; `watchfiles` to watch the queue
- SQLite (the existing index) and file locks — unchanged
- `structlog`, optionally OpenTelemetry
- Packaging: extra `server = [fastapi, uvicorn, sse-starlette]`

**Frontend**
- React 19 + Vite + TypeScript
- TanStack Query (server state), Zustand (local UI state)
- Tailwind v4 + shadcn/ui
- Zod + `openapi-typescript` → `web/src/api/generated`
- An SSE hook instead of a hand-written `EventSource`

## 5. API contract

Version: `/api/v1`. Errors: `{ "ok": false, "error": { "code", "message" } }`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | version, write mode, builder |
| GET | `/products`, `/detectors` | product and detector maps |
| GET | `/tasks?limit=` | task list |
| POST | `/tasks` | create a task |
| GET | `/tasks/{id}` | detail (story, proof, rail, runs) |
| GET | `/tasks/{id}/runs` | run summaries |
| GET | `/tasks/{id}/export/{kind}` | download a run artifact |
| GET | `/tasks/{id}/artifacts/{name}` | runtime artifact |
| POST | `/actions` | add-context, ask, commentary, discussion, approve-plan, release, deliver, confirm, team-verify |
| POST | `/readiness` | repository readiness |
| POST | `/sources` | import GitHub/Jira/detector |
| GET/POST | `/settings/builder` | builder/planner settings |
| GET | `/metrics`, `/ledger` | observability |
| GET | `/events` | SSE: queue and run updates |
| POST | `/ask/stream` | streamed Mira answer |

Requirements:
- writes require `Authorization: Bearer <local token>` (or `X-Works-Write` plus the token);
- localhost / named pipe only; no CORS;
- idempotency: `Idempotency-Key` for `POST /tasks` and `POST /actions`;
- `GET /tasks/{id}` returns the same fields as today's `_task_detail`.

## 6. Phases

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
- [ ] Local token and request-origin checks.
- [ ] Shared `asyncio.Lock` and file locks for writes.
- [ ] Idempotency.
- [ ] Long actions (Mira, team verify, readiness) via `asyncio.to_thread` plus job status.

**Done when:** create/approve/release UI flows work through the new API.

### Phase 4 — live updates (1 day)
- [ ] `LiveState` → SSE `text/event-stream` with a heartbeat.
- [ ] `POST /ask/stream` as a FastAPI streaming response.
- [ ] Reconnect with backoff on the client.

**Done when:** an open tab updates without polling and survives a dropped stream.

### Phase 5 — TypeScript frontend (3–4 days)
- [ ] `tsconfig`, `strict: true`, optional ESLint, `vitest`.
- [ ] `openapi-typescript` → `web/src/api/generated/schema.d.ts`.
- [ ] Thin client `web/src/api/client.ts` (fetch plus token).
- [ ] TanStack Query: `useTasks`, `useTaskDetail`, `useActions`, `useMetrics`.
- [ ] SSE hook `useEvents`.
- [ ] Migrate screens one by one: Queue → Story → Evidence → Release → Session → Settings.
- [ ] Delete `lib/api.js` after the move.

**Done when:** `tsc --noEmit` and `vite build` are green and the UI runs on the new API.

### Phase 6 — process split (2 days)
- [ ] `works daemon start|stop|status`, pidfile, port, log.
- [ ] CLI: `--standalone` (as today) and `--daemon` (HTTP).
- [ ] UI assets: the backend serves `dist` via `StaticFiles`.
- [ ] One writer: `dispatch --watch` runs only inside the daemon.

**Done when:** UI and `dispatch` run together without races; closing the UI does not kill runs.

### Phase 7 — cutover (1 day)
- [ ] FastAPI is the only server; the stdlib server is deleted.
- [ ] `uvicorn` and `sse-starlette` are declared (extra `server`).
- [ ] CI: `tsc --noEmit`, contract tests, daemon smoke test.
- [ ] Docs: `docs/guides/ui.md`, `docs/reference/layout.md`.

**Done when:** CI is green, `works ui` starts the daemon, old code is gone.

### Phase 8 — hardening (2 days)
- [ ] Load smoke: 200 tasks, 20 parallel SSE clients.
- [ ] Errors: timeouts, request cancellation, retries.
- [ ] Security: token, Host/Origin checks, request size limits.
- [ ] Metrics: API latency, queue depth, active runs.
- [ ] Final full test run and ADR update.

## 7. Structure after the migration

```
src/works/interfaces/http/
  app.py            # FastAPI, lifespan, wiring
  routes/           # tasks, actions, settings, sources, observability
  live.py           # SSE / ask stream
  schemas/          # Pydantic request/response models
  security.py       # local token
web/src/
  api/              # client.ts, generated/, hooks (TanStack Query)
  app/              # shell, routing
  features/         # queue, story, evidence, release, session, settings
  ui/               # primitives
  styles/
```

## 8. Testing

- Backend: pytest with `httpx` ASGI, old-vs-new contract tests, SSE tests.
- Frontend: `tsc --noEmit`, `vitest` for hooks and pure functions, build.
- E2E (optional): Playwright against demo data.
- CI: separate `check`, `web`, `contract` and `docker` jobs.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Long actions block HTTP | `asyncio.to_thread`, job status, limits |
| Double writes (UI + dispatch) | one daemon owns the queue; standalone CLI is manual only |
| Contract drift | contract tests on recorded fixtures |
| SSE through proxies/antivirus | heartbeat, reconnect, polling fallback |
| Windows paths and `claude.exe` | do not change adapter logic |
| Long UI migration | migrate screen by screen, keep routing compatible |
| Losing CLI simplicity | `--standalone` stays the default for one-shot runs |

## 10. Estimate

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

## 11. Definition of done

- [ ] `works ui` starts the daemon; the UI runs on `/api/v1`.
- [ ] CLI: both `--standalone` and `--daemon` work.
- [ ] Contract tests: old and new JSON match.
- [ ] `pytest`, `ruff`, `mypy`, `tsc --noEmit`, `vite build` are green.
- [ ] CI is green; the stdlib server is deleted.
- [ ] ADR-016 and updated guides are committed.

## 12. Rollback

- Before Phase 7: the old server stays; switch with the `WORKS_HTTP=legacy` flag.
- After cutover: a `pre-fastapi` tag plus rollback instructions in the ADR.
