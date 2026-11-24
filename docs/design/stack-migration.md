# Migrating to a separate backend and frontend

**Status:** plan (not started)
**Date:** 2026-11-24
**Companion:** [`stack-migration-review.md`](stack-migration-review.md) — the code review that
prompted the corrections below.

## 1. Goal

Split the product into two processes and two codebases:

- **backend** — a local daemon (`works daemon`) in Python that owns the queue, runs, jobs, SSE and
  settings;
- **frontend** — a React/TypeScript SPA, a thin typed client.

The engine (`domain/`, `application/`, `adapters/`) is **not rewritten**. The daemon wraps it.

## 2. Principles

1. The event log and run artifacts stay the source of truth.
2. The daemon owns the queue, runs and gates. A standalone CLI is allowed only when no daemon owns
   the home.
3. The CLI stays a first-class client; it may run in-process or attach over HTTP.
4. Local-only: loopback bind, token-gated writes, no CORS.
5. Event log for integration, not service-to-service calls.
6. API versioned as `/api/v1`; client types generated from OpenAPI.
7. No microservices, Redis, Postgres, GraphQL or cloud.
8. The old stdlib server is removed at cutover; rollback is a git tag, not a dual runtime.

## 3. Target architecture

```
Browser ── SPA (React/TS) ── HTTP/JSON + SSE ─┐
                                             │
CLI (works …) ── in-process (--standalone) ──┤
   └─ or HTTP client (--daemon) ─────────────┤
                                             ▼
                                  works daemon (FastAPI/Uvicorn)
                                  ├─ /api/v1 REST + SSE
                                  ├─ job executor (runs, long actions)
                                  ├─ optional scheduler (queued tasks)
                                  ├─ per-job Supervisor (engine)
                                  └─ queue, file locks, event log
```

Production: **daemon + browser**. Development: **Uvicorn + Vite + browser**.

## 4. Stack

**Backend**
- Python **3.12** (current CI) with 3.13 tested; 3.14 stays out until `pyproject` allows it.
- FastAPI, Uvicorn, Pydantic v2, `sse-starlette`, `asgi-lifespan` (tests).
- asyncio for the HTTP layer; the engine is async but its adapters block, so runs execute in
  dedicated worker threads (§6).
- SQLite index (`TaskIndex`) and file locks — unchanged.
- Packaging: extra `server = [fastapi, uvicorn, sse-starlette]`.

**Frontend**
- React 19 + Vite + TypeScript (strict for new files; `allowJs` during migration).
- TanStack Query for server state; Zustand optional, only if local state grows.
- Keep the existing CSS; **no Tailwind/shadcn rewrite** in this migration.
- Zod + `openapi-typescript` → `web/src/api/generated`.
- Vitest + Testing Library + jsdom for hooks and pure helpers.
- SSE hook; `ask` uses streaming `fetch`, not `EventSource`.

## 5. Contracts

### 5.1 Endpoints (`/api/v1`)

| Method | Path | Auth | Result |
|---|---|---|---|
| GET | `/health` | read | version, write mode, builder |
| GET | `/products`, `/detectors?refresh=` | read | maps |
| GET | `/tasks?limit=` | read | list |
| POST | `/tasks` | write | 201 created / 200 existing |
| GET | `/tasks/{id}` | read | full detail |
| GET | `/tasks/{id}/runs` | read | run summaries |
| GET | `/tasks/{id}/export/{kind}` | read | file download |
| GET | `/tasks/{id}/artifacts/{name:path}` | read | runtime artifact |
| POST | `/actions` | write | 200 sync or 202 + job |
| GET | `/jobs/{id}`, `DELETE /jobs/{id}` | read/write | job status / cancel |
| POST | `/readiness` | write | 202 + job |
| POST | `/sources` | write | 202 + job |
| GET | `/settings/builder` | read | current settings |
| POST | `/settings/builder` | write | saved settings |
| POST | `/session` | none | exchanges bootstrap token for a cookie |
| GET | `/events` | read | SSE |
| POST | `/ask/stream` | write | SSE `delta`/`done`/`error` |
| POST | `/runs` | write | 202 + job (run one task) |
| POST | `/dispatch` | write | 202 + job (claim ready tasks) |
| GET | `/runs/{run_id}` | read | run status and summary |
| GET | `/metrics`, `/ledger` | read | factory metrics and ledger |
| GET | `/system/metrics` | read | API/job/SSE telemetry (new) |
| GET | `/openapi.json` | none | schema for client generation |

`HEAD` is supported for static and download routes. An unversioned `/health` alias may exist for
`works ui`, but `/api/v1` is canonical.

Embedded URLs (artifacts, exports) are built by one helper and include the version prefix.

### 5.2 Actions

There are **nine** existing actions; `deploy` is added to close the Release gap.

| Action | Kind |
|---|---|
| `add-context` | sync |
| `approve-plan` | sync |
| `release` | sync |
| `ask` | dedicated `POST /ask/stream` (SSE) |
| `commentary` | job (model call, up to 180 s) |
| `discussion` | job (model call, up to 180 s) |
| `deliver` | job (git/network) |
| `confirm` | job (network/commands) |
| `team-verify` | job (subprocess) |
| `deploy` | job (command) — new |

`run-readiness` is **not** an action: the Evidence panel calls `POST /readiness` with the task’s
repository.

### 5.3 Errors

Body: `{ "ok": false, "error": { "code": "...", "message": "..." } }`.

| Source | Status |
|---|---|
| request validation / bad body | 400 (or FastAPI 422 for schema errors) |
| missing/invalid auth | 401 |
| policy refusal | 403 |
| not found | 404 |
| state/conflict/idempotency replay conflict | 409 |
| missing model key, agent-core, swarm, docker daemon | 503 |
| `HarnessError` / worker crash | 502 |
| unexpected | 500 with a request id |

Add `AuthError` (401/403) and `UnavailableError` (503) to `domain/errors.py`; keep `ConfigError`
for user-fixable configuration. The client reads `error.message` (never `[object Object]`) and maps
`code` to the existing toast wording.

### 5.4 SSE

`GET /events` sends `id`, named `event` and JSON `data`:

| Event | Data |
|---|---|
| `queue.changed` | `{}` |
| `task.changed` | `{"task_id": "t-…"}` |
| `run.changed` | `{"task_id": "t-…", "run_id": "r-…"}` |
| `job.changed` | `{"job_id": "j-…", "status": "running"}` |
| `settings.changed` | `{}` |
| `heartbeat` | `{"ts": "…"}` every 15 s |
| `resync` | `{"epoch": "…", "reason": "gap"}` |

The source of truth is `events.jsonl` plus the job store: a mapper tails new events and emits the
named events. A ring buffer keeps the last 200 events per epoch; `Last-Event-ID` older than the
ring gets `resync`, and the client refetches the open task/list.

### 5.5 Auth

- **Persistent token** `.works/state/http-token` (owner-only) for CLI `Authorization: Bearer`.
- **Bootstrap token** per `works ui` launch, single-use, in `?bootstrap=…`. `POST /session`
  validates it, sets an HttpOnly `SameSite=Strict` cookie (random session id kept in memory), and
  the SPA drops the URL token.
- Reads are allowed on loopback without a cookie. All writes require the session cookie or Bearer.
- Reject non-loopback `Host`/`Origin`; `--host` accepts only loopback unless `--allow-remote` is
  passed explicitly.
- Windows: set file permissions with an ACL (`icacls`) and fall back to `chmod` where possible.
- `.works/state/` is gitignored.

### 5.6 Jobs

- Statuses: `queued`, `running`, `succeeded`, `failed`, `cancelled`.
- Persisted in `.works/state/jobs/*.json`; on startup, `running` jobs become `failed`
  (`daemon restarted`) and stale owners are reconciled.
- Max 2 concurrent jobs; one job per task (per-task lock in the registry).
- Cancellation is cooperative: the job gets a cancel flag and the process registry kills the active
  child. Document that a job cannot be cancelled after a side effect (push, PR, comment, deploy).
- Job payload: id, action, task_id, status, timestamps, result, error, `log_tail`, `cancelable`.

### 5.7 Runs and scheduler

The daemon owns runs:

- `POST /runs` `{task_id, approve_plan, scenarios, quarantine}` → job of kind `run`.
- `POST /dispatch` `{limit}` → job that claims ready tasks one by one (no HTTP long-poll loop).
- Optional `works daemon --schedule <seconds>` enables a scheduler that dispatches queued tasks when
  enabled in settings. Off by default.
- `works dispatch --watch` works only in `--standalone`; if a daemon owns the home it exits with a
  clear message.

## 6. Execution and concurrency

`Supervisor.run` is `async def`; its adapters (git, verifier, harness processes) block.

- Each run job builds **its own Supervisor** from current settings via a factory (no argparse, no
  shared mutable supervisor) and executes it in a dedicated worker thread:
  `asyncio.run(supervisor.run(...))`.
- The event loop stays free for HTTP, SSE and heartbeats; a 30-second run must not delay a 1-second
  heartbeat or `GET /tasks`.
- Job executor: 2 workers, per-task locks, file locks unchanged.
- Settings saved during a run apply to the next job; active jobs are listed and left alone.
- Standalone CLI refuses to write when a daemon owns the home (`daemon.json` + lock file).

## 7. File mapping

| Today | After |
|---|---|
| `interfaces/api/server.py` | `interfaces/api/app.py` + `routes/` (deleted) |
| `interfaces/api/read.py` | `interfaces/api/routes/{tasks,observability}.py` |
| `interfaces/api/write.py` | `interfaces/api/routes/{actions,sources,settings,readiness}.py` |
| `interfaces/api/downloads.py` | `interfaces/api/routes/downloads.py` (`FileResponse`) |
| `interfaces/api/static.py` | `StaticFiles` + `/mira.svg` from `dist` |
| `interfaces/api/live.py` | `interfaces/api/live.py` (SSE mapper + broadcaster) |
| `interfaces/api/presenters/*` | keep; typed response models |
| `interfaces/cli/commands/ui.py` | start/attach the daemon |
| `interfaces/cli/commands/daemon.py` (new) | start/stop/status |
| `web/src/lib/api.js` | `web/src/api/client.ts` |
| `web/src/App.jsx` | shell; `useEvents` instead of `EventSource` |
| `scripts/agent_chat_worker.py`, `team_verify_worker.py`, `swarm_adapter.py` | packaged workers (not repo-relative) |
| `flows/` | default flows packaged and bootstrapped into a new home |

`mira.svg` moves to `web/public/` so Vite emits it into `dist`; the static special case disappears.
Delete `server.py`, `read.py`, `write.py`, `downloads.py`, `static.py`, `lib/api.js` and the legacy
tests at cutover.

## 8. Phases

Every item names the artifact; each phase ends with a **gate**.

### Phase 0a — fixtures and canonicalizer (done)

- [x] `scripts/seed_home.py`: fixed clock, fixture repo, flows, scenarios, five tasks (queued,
  planning, proved, released + delivered + confirmed + deployed, blocked) and a flake.
- [x] `tests/contract/canonicalize.py`: masks timestamps, ids, hashes (short and long), commits,
  durations, command output, markdown proofs, home/repo/python paths and any Windows absolute path;
  unit tests cover each rule.
- [x] `scripts/capture_api_fixtures.py`: starts the legacy server on the seed home and writes
  canonical GET fixtures; `--check` reseeds and compares.
- [x] `tests/contract/test_baseline.py`: fixture presence, task states, every detail section,
  released/blocked payloads, and a leak check for timestamps and absolute paths.
- [ ] POST fixtures: added with the action tests in Phase 3b, against isolated copies of the home.

**Gate (met):** `pytest tests/contract -q`; `scripts/capture_api_fixtures.py --check` -> 16 fixtures
match.

### Phase 0b — frontend toolchain (done)

- [x] `web/package.json`: TypeScript 5.9, React types, TanStack Query, Zod, `openapi-typescript`,
  Vitest, Testing Library and jsdom; scripts `dev/build/typecheck/test/generate:api`; the lockfile is
  regenerated and committed (`npm ci --dry-run` is clean).
- [x] `web/tsconfig.json`: strict for TS files, `allowJs`, `jsx: react-jsx`,
  `moduleResolution: bundler`, Vitest and jest-dom types.
- [x] `web/vite.config.js`: Vitest with jsdom and a setup file; a toolchain test runs.
- [x] `.github/workflows/ci.yml`: a `web` job runs install, typecheck, unit tests, build, and fails if
  the committed `dist` changes.
- [ ] `scripts/dump_openapi.py`: moved to Phase 1, because it needs the FastAPI app.
- [ ] `--extra server` in CI: moved to Phase 1 with the first HTTP tests.

**Gate (met):** `npm ci && npm run typecheck && npm test && npm run build`.

### Phase 1 — daemon skeleton (done)

- [x] `pyproject.toml`: `server = [fastapi, uvicorn, sse-starlette]`; `httpx` in dev; lockfile
  updated; CI syncs `--extra dev --extra server`.
- [x] `interfaces/api/app.py`: `create_app(paths, writable)`, lifespan state, versioned
  `/api/v1/health`, versioned OpenAPI URL.
- [x] `interfaces/api/wiring.py`: `AppState`/`build_state` (paths, queue, ledger, settings). The
  per-job supervisor factory moves to Phase 3a, where jobs exist.
- [x] `interfaces/api/schemas/health.py` and `routes/health.py` reuse the read presenter.
- [x] `interfaces/cli/commands/daemon.py` + `cli/parser/daemon.py`: `works daemon --host --port
  --write --allow-remote`; non-loopback binds are refused by default.
- [x] `scripts/dump_openapi.py` writes `docs/reference/openapi.json`; CI checks it is current and
  smokes `works --help` / `works version`.
- [x] Tests use FastAPI `TestClient` as a context manager so the lifespan runs (no extra dependency).

**Gate (met):** `pytest tests/unit/interfaces/api`; `works daemon --help`; health matches the legacy
keys; `dump_openapi.py --check`.

### Phase 2 — read API (done, perf deferred)

- [x] `schemas/tasks.py`: `TaskSummary`, `TaskList`, `RunSummary`, `RunList`, `TaskDetail` with every
  detail section; evolving nested sections stay as JSON objects so no field is dropped.
- [x] `routes/tasks.py`, `routes/maps.py`, `routes/observability.py`, `routes/downloads.py`;
  downloads reuse the confined resolver and return content type plus disposition.
- [x] Artifact URLs are versioned: the presenter takes a prefix, the new API uses `/api/v1`, and
  the contract canonicalizer treats `/api` and `/api/v1` as equal.
- [x] Contract tests seed the home, call the new app with `TestClient`, and compare canonicalized
  JSON for health, list, every detail, every run list, maps, metrics and ledger; a test fetches the
  artifact URL returned in detail and checks traversal is refused.
- [ ] `TaskIndex`/`fast_read` for list/detail, readiness/release caching, and the 10,000-task list
  budget move to Phase 8, where performance is measured.

**Gate (met):** `pytest tests/contract tests/unit/interfaces/api`; 19 contract tests pass. The
performance gate is tracked in Phase 8.

### Phase 3a — jobs, security, session (done, subprocess kill deferred)

- [x] `WorksPaths.state` + `.works/state/` creation and gitignore.
- [x] `security.py`: owner-only persistent token, one-time bootstrap token, `POST /session` with an
  HttpOnly `SameSite=Strict` cookie, Bearer support, loopback Host and Origin checks.
- [x] `require_write` dependency: 401 without a token, 403 in read-only mode.
- [x] `jobs.py`: two-worker executor, persisted statuses, one job per task, cancellation flag,
  startup reconciliation that fails orphans and releases their queue owner.
- [x] `domain/errors.py`: `AuthError`, `ReadOnlyError`, `UnavailableError`; the app maps
  `WorksError` to the §5.3 statuses with a JSON error body.
- [x] `GET/DELETE /api/v1/jobs/{id}` and security/jobs tests (bootstrap, cookie, bearer, host,
  origin, read-only, success, failure, cancel, lock, reconcile).
- [ ] Killing an in-flight child process on cancel is wired with the actions in Phase 3b, because no
  current job starts a subprocess yet.

**Gate (met):** `pytest tests/unit/interfaces/api`; crash/restart reconciliation test passes.

### Phase 3b — actions, readiness, sources, settings (done, full-run smoke deferred)

- [x] `routes/actions.py`: add-context, approve-plan and release answer synchronously; commentary,
  discussion, deliver, confirm, team-verify and the new deploy run as jobs with 202 + job id. `ask`
  is refused with a hint to the streaming endpoint.
- [x] `routes/readiness.py`: `POST /readiness` resolves a task or repository and runs the gate as a
  job.
- [x] `routes/sources.py`: GitHub/Jira/detector imports run as jobs and reuse the legacy intake.
- [x] `routes/settings.py`: GET returns builder health; POST saves settings for the next job.
- [x] One `WorksError` handler covers the status table from §5.3.
- [x] `scripts/smoke_api.py`: seeds a home, adds context, approves a plan, releases a proved task
  and runs readiness through the new API.
- [ ] The end-to-end create → fake-harness run → release → deliver → confirm → deploy smoke moves to
  Phase 6, when `POST /runs` exists.
- [ ] `Idempotency-Key` and killing an in-flight child on cancel move to Phase 6/8.

**Gate (met):** `pytest tests/contract tests/unit/interfaces/api`; `python scripts/smoke_api.py`.

### Phase 4 — live updates (2 days)
- [ ] `live.py`: event mapper (tail `events.jsonl`, job store, settings), ring buffer, epoch,
  `resync`; heartbeat.
- [ ] `routes/events.py`: named SSE, `Last-Event-ID`, disconnect handling.
- [ ] `routes/ask.py`: bridge `ask_mira_stream` through a thread; `delta/done/error`.
- [ ] Tests: task/run/job events, heartbeat, gap → `resync`, stream cancel.

**Gate:** `pytest tests/unit/interfaces/api/test_sse.py`.

### Phase 5a — frontend toolchain and client (2 days)
- [ ] `web/src/api/generated/schema.ts` from OpenAPI (committed); CI regenerates and fails on diff.
- [ ] `client.ts`: cookie credentials, typed errors, `Idempotency-Key`.
- [ ] `hooks.ts`: `useTasks`, `useTaskDetail`, `useActions`, `useJob`, `useMetrics`, `useEvents`.
- [ ] `useJob` state machine: queued/running/succeeded/failed/cancelled, progress/log, refresh on
  success, disabled while busy.
- [ ] Vitest setup and tests for client/hooks with mocked fetch.

**Gate:** `npm run typecheck && npm test`.

### Phase 5b — screens (5 days)
- [ ] Queue (search, filters, grouping/counts, mobile new task, live dot).
- [ ] Story (route, receipts, replay, present mode, copy link, memory badge, blocked callout).
- [ ] Evidence (pipeline, verdict, findings, challenge, commands, change, readiness, features,
  artifacts/lightbox, timeline, exports, policy/risk/decision/residual/cost/verifier/team/LAIX).
- [ ] Release (packet, gate, deliver/confirm/deploy as jobs, compare runs, deployment/LAIX).
- [ ] Session (transcript, chapters, ask stream, review/commentary jobs, add context, run log, rail).
- [ ] Settings (runtime/provider, verifier split, planner modes/critic, workspace, read-only).
- [ ] Dialogs: Factory metrics/ledger, Run, Event, Palette, Help, Import; toasts and shortcuts.
- [ ] Delete `lib/api.js`; every parity row from §18 has a test.

**Gate:** `typecheck && test && build`, plus the parity matrix.

### Phase 6 — processes, runs, Windows lifecycle (4 days)
- [ ] `daemon.json` `{pid, host, port, home, started_at, token_path}`; pid reuse check; graceful stop
  (`CTRL_BREAK_EVENT` on Windows, health identity before kill); single-instance lock.
- [ ] Start detached with `cwd=home`, allow-listed env snapshot, log redirection; relative repos
  resolve against `home`.
- [ ] `POST /runs`, `POST /dispatch`, `GET /runs/{id}`; optional `--schedule`; `dispatch --watch`
  guarded under a daemon.
- [ ] CLI `--daemon` waits for jobs (`run_job_and_wait`), prints the same JSON, maps exit codes;
  `--standalone` remains default and refuses when a daemon owns the home.
- [ ] Static: `dist` at `/`, `/mira.svg` from `dist`, API 404 before SPA fallback.

**Gate:** daemon + UI + `POST /dispatch` concurrently; no lock conflicts; kill the UI, run survives;
restart daemon, stale jobs/owners reconciled.

### Phase 7 — cutover, packaging, tests (2 days)
- [ ] Delete old HTTP modules; migrate/delete `tests/unit/interfaces/api/test_ui.py` and friends.
- [ ] CI runs `pytest` in the cutover gate; coverage stays ≥ 80%.
- [ ] Package worker scripts and default flows; resolve via `importlib.resources`; wheel test asserts
  `dist/index.html`, workers and flows are present.
- [ ] Installed-wheel smoke: `works ui` + `works ask` + `works team verify` in a temp home.
- [ ] CI checks `dist` freshness (build then `git diff --exit-code`).
- [ ] Docs: `ui.md`, `runbook.md`, `layout.md`, README commands; tag `pre-fastapi`.

**Gate:** CI green; wheel smoke passes.

### Phase 8 — hardening (2.5 days)
- [ ] 10,000-task load test and 20 SSE clients; p95 targets.
- [ ] Cancel-with-side-effects, daemon crash, stale owner, token rotation tests.
- [ ] Body-size middleware (chunked included), job timeouts, Origin/Host tests.
- [ ] Logging: request_id/job_id, uvicorn access logs through the same formatter.
- [ ] Final full runs and ADR update.

**Gate:** all §17 checks on a fresh clone.

## 9. Frontend mechanics

- `allowJs` with per-file migration; new files strict `.ts/.tsx`.
- Query keys `["tasks"]`, `["task", id]`, `["job", id]`, `["metrics"]`; invalidate on named SSE
  events and after mutations.
- Long actions use `useJob`; never toast success before completion.
- `ask` streams with `fetch` + `ReadableStream`; no `EventSource` for POST.
- Generated types committed; CI regenerates and diffs.
- npm scripts: `dev`, `build`, `typecheck`, `test`, `generate:api`.
- Vite proxy `/api` → `http://127.0.0.1:8765`; production same-origin.

## 10. Structure after migration

```
src/works/interfaces/api/
  app.py wiring.py live.py jobs.py security.py
  routes/ health tasks actions readiness sources settings observability downloads events ask runs
  schemas/ health tasks actions events settings common
  presenters/ story tasks thread
src/works/interfaces/cli/
  main.py parser/ commands/ (incl. daemon.py) render.py
src/works/interfaces/ui/static/   # favicon, dist/
web/src/
  api/ client.ts generated/ hooks.ts events.ts
  app/ features/ ui/ lib/ styles/
tests/ unit/ contract/ integration/ e2e/
```

## 11. Testing and CI

- Backend: `httpx` + `asgi-lifespan`; contract fixtures on the seed home; SSE/job/security tests.
- Frontend: `tsc --noEmit`, Vitest (jsdom), build; Playwright optional for the demo flow.
- CI: `check` (`--extra dev --extra server`), `web`, `contract`, `docker-verifier`, `benchmark`,
  `security`; coverage gate 80%; `dist` freshness.
- Contract canonicalizer owns all nondeterminism; no “normalize timestamps” hand-waving.

## 12. Packaging

- Extra `server`; `works ui` prints an install hint if missing.
- Workers and default flows ship in the wheel; no repo-relative paths at runtime.
- Wheel-content test and installed-wheel smoke.
- `dist` is built in CI and checked for drift.

## 13. Observability

- Reuse `config/logging.py`; add `request_id`, `job_id`; route Uvicorn logs through it.
- `/metrics` stays factory metrics; `/system/metrics` adds latency, queue depth, active runs, job
  failures, SSE clients.
- Targets: p95 read 150 ms, p95 write 300 ms (sync actions only), 20 SSE clients, memory 300 MB,
  10k-task list < 100 ms.

## 14. Security

- Loopback only by default; token-gated writes; HttpOnly cookie; Host/Origin checks.
- Body limit middleware (64 KB writes, chunked included).
- Artifact path confinement (already in `downloads.py`).
- No secrets in UI state; `.works/state/` ignored; Windows ACL for the token.
- Read-only mode still works (`readonly` in health, writes 403).

## 15. Risks

| Risk | Mitigation |
|---|---|
| Blocking engine freezes the loop | per-job thread + `asyncio.run`; heartbeat test |
| Two writers | daemon-owned queue; standalone guarded by home lock |
| Cancellation after side effects | documented semantics + cancel flag before effects |
| Crash leaves owners | persisted jobs + startup reconciliation + PID/start-time check |
| Contract drift | seed home + canonicalizer + complete schemas |
| Stale `dist` | CI build + diff check |
| Settings not applied | per-job supervisor factory + test |
| Windows lifecycle | `daemon.json`, cwd=home, env snapshot, graceful stop |
| UI regressions | parity matrix with per-screen tests |
| Schedule slip | 28–35 days, 20% contingency |

## 16. Estimate

| Phase | Days |
|---|---|
| 0a fixtures/canonicalizer | 1 |
| 0b OpenAPI/toolchain | 1 |
| 1 skeleton | 1.5 |
| 2 read API | 3 |
| 3a jobs/security | 3 |
| 3b actions/readiness/sources/settings | 2 |
| 4 live | 2 |
| 5a toolchain/client | 2 |
| 5b screens | 5 |
| 6 processes/runs/Windows | 4 |
| 7 cutover/packaging/tests | 2 |
| 8 hardening | 2.5 |
| **Subtotal** | **29** |
| Contingency 20% | ~6 |
| **Total** | **~35 days** |

## 17. Definition of done

- [ ] `works daemon` + UI on `/api/v1`; CLI both modes; standalone guarded.
- [ ] Runs and dispatch through the daemon; jobs persisted and reconciled.
- [ ] Contract tests: canonicalized parity for every endpoint.
- [ ] `pytest` (coverage ≥ 80%), `ruff`, `mypy`, `tsc --noEmit`, `vitest`, build all green.
- [ ] CI green; old server and old tests deleted; wheel smoke passes.
- [ ] Parity matrix complete; `dist` fresh; docs and ADR updated.

## 18. Parity matrix

| Screen | Files | API | Actions | Test |
|---|---|---|---|---|
| Queue + grouping | `features/queue/*` | `GET /tasks` | — | list/filter/sort |
| New task | `dialogs/task-composer` | `POST /tasks` | — | create + duplicate |
| Import | `dialogs/import` | `POST /sources` | job | counts + duplicate |
| Story | `features/story/*` | `GET /tasks/{id}`, events | — | states, replay, copy link |
| Evidence | `features/evidence/*` | detail, `/readiness`, exports, artifacts | readiness job | cards + downloads |
| Release | `features/release/*` | detail, `/actions` release/deliver/confirm/deploy | jobs | each job state |
| Session | `features/session/*` | detail, `/ask/stream`, `/actions` | ask stream, commentary, discussion, add-context | stream + jobs |
| Settings | `features/settings/*` | `/settings/builder` | save | validation + apply |
| Factory | `dialogs/factory` | `/metrics`, `/ledger` | — | payload |
| Run/Event/Palette/Help | dialogs | detail | — | open/close |
| Read-only | shell | health | writes 403 | mode |

## 19. Decisions

- Package name: `interfaces/api` (not `http`).
- Command: `works daemon` (not `worksd`).
- No dual runtime: rollback by `pre-fastapi` tag.
- Python: 3.12 primary, 3.13 tested; 3.14 later.
- CSS stays; no Tailwind/shadcn.
- Runs are daemon-owned; standalone is guarded.
- Long actions are jobs; `ask` streams.
- API path versioned; embedded URLs versioned.

## 20. Rollback

- Until Phase 7 the old server is still in the tree; switch paths by reverting the phase commit.
- After cutover: check out `pre-fastapi` and reinstall the previous version.

## 21. Review traceability

Every finding in [`stack-migration-review.md`](stack-migration-review.md) is addressed above:

- blockers 1–6: §6, §5.7, §5.2/§8, §8 Phase 3b, §4/§8 Phase 0b, §8 Phase 7;
- contract/schema/URL gaps: §5.1, §8 Phase 0a/2;
- auth/jobs/SSE: §5.4–5.6;
- static/packaging/metrics/CLI/Windows: §7, §8 Phase 6–7, §12–13;
- parity/estimate: §16–18.
