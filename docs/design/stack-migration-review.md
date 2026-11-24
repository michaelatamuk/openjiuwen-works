# Review: `docs/design/stack-migration.md`

## Verdict

**No — not executable as written.** The direction (keep the engine, put a thin FastAPI daemon in front, generate the client types, keep one local writer) is sound, and the file mapping in §7 mostly matches the repository. But three gate-breaking problems remain: the plan misstates the engine as synchronous, it claims the daemon owns runs and a scheduler without defining any run/scheduler API, and its Phase 3 smoke test and Phase 6 gate cannot pass. Fix the blockers and expand the contract, auth, job and static sections before starting Phase 0.

## Findings

1. **Blocker — the engine is async, not "synchronous/blocking"; `asyncio.to_thread` will not run it.**  
   **Plan:** §6 ("The engine is synchronous/blocking. Never call `Supervisor.run` on the event loop: run it in a dedicated thread (`asyncio.to_thread` ...)"), and §15.  
   **Reality:** `Supervisor.run` is `async def` (`src/works/application/supervisor/core.py:110`); so are `_execute`, `_build`, `_verify`, `_propose` and `_challenge` (`.../supervisor/execution.py:38`, `.../verification.py`). `asyncio.to_thread(supervisor.run, ...)` calls the async function and returns an un-awaited coroutine; it does not execute the run. Conversely, `await supervisor.run(...)` on the event loop blocks on synchronous subprocess and git work (`src/works/adapters/processes/runner.py:121`, `src/works/adapters/git/repo.py`), freezing SSE and every other request.  
   **Why it matters:** the central concurrency design is wrong in both directions; jobs either never run or the daemon stops serving.  
   **Fix:** choose one explicit execution model: a worker thread per job that runs `asyncio.run(supervisor.run(...))` with a supervisor built for that job, or convert all adapter calls reached from `Supervisor.run` to `await asyncio.to_thread(...)` and keep the run on the loop. Add a test that a 30-second fake run does not stop a 1-second heartbeat or a parallel `GET /tasks`.

2. **Blocker — no API or phase implements the claimed "queue, runs and scheduler".**  
   **Plan:** §1 ("owns the queue, runs, SSE and long actions"), §3 ("queue and scheduler (asyncio)"), §5.1 (REST table has no run or dispatch endpoint), §8 Phase 6 gate ("a queued dispatch run at the same time").  
   **Reality:** the only run starters are the CLI `works run` and `works dispatch --watch` (`src/works/interfaces/cli/commands/run.py:22,101`). The REST table has no `POST /runs`, no `POST /dispatch`, no scheduler phase, and no job type for a run. Phase 6 simultaneously requires a queued dispatch run and says `dispatch --watch` must refuse to run when the daemon owns the queue (`stack-migration.md:285-289`).  
   **Why it matters:** the daemon cannot actually own runs, so Phase 6 cannot be demonstrated and the target architecture is false.  
   **Fix:** either add a run endpoint and a scheduler with explicit selection, builder/settings and claim behaviour, plus a phase for it, or remove "runs/scheduler" from the goal and delete the dispatch-run clause from the Phase 6 gate.

3. **Blocker — `scripts/smoke_api.py` (Phase 3) cannot pass.**  
   **Plan:** §8 Phase 3 ("`scripts/smoke_api.py`: create → approve-plan → release → confirm against a demo home", `stack-migration.md:242`).  
   **Reality:** `POST /tasks` creates a `queued` task only (`src/works/interfaces/api/write.py:20-70`). `approve_plan` requires state `planning` and a `plan.drafted` event (`src/works/application/approvals/gates.py:28-33`). `release` needs a proved run, and `confirm` needs a delivered run (`src/works/application/delivery/confirm.py`, `deliver.py`). No step in the smoke test drafts a plan, runs the engine or delivers.  
   **Why it matters:** the Phase 3 gate is a hard stop that will fail on the first try and hide real regressions.  
   **Fix:** seed a planning task with a recorded plan, a proved run, and a delivered run in the demo home, or make the smoke test run the full fake-harness loop (`FakeHarness` + `fixtures/traces/fix-add.json`) and assert each response. Make it deterministic and offline.

4. **Blocker — the action taxonomy is wrong: nine actions exist, two are long model calls, and readiness is not an action.**  
   **Plan:** §5.1 ("all eight actions"; long actions are `ask`, `team-verify`, `readiness`, `deliver`, `confirm`), §8 Phase 3 (`stack-migration.md:234`).  
   **Reality:** `src/works/interfaces/api/write.py:81-185` implements nine actions: `add-context`, `ask`, `commentary`, `discussion`, `approve-plan`, `release`, `deliver`, `confirm`, `team-verify`. `commentary` and `discussion` call `_collect` with a 180-second subprocess timeout (`src/works/application/assistant/chat.py:59,107`), so they are long actions, not synchronous. Readiness is a separate `POST /api/readiness` (`write.py:188`). The UI's Evidence panel calls `onAction("run-readiness")` (`web/src/features/evidence/Evidence.jsx:63`), which is not implemented by `run_action` and currently returns "unknown action".  
   **Why it matters:** the new API will either block for three minutes on a POST advertised as synchronous, or the UI will get 400/202 with no handler; the count in the plan is simply wrong.  
   **Fix:** enumerate all nine actions and classify each as sync or job; move `commentary`/`discussion` to jobs; add a real `POST /readiness` flow (repo from the task or an explicit field) and replace the `run-readiness` UI call; add one contract test per action.

5. **Blocker — the Phase 5 frontend gate cannot pass with the declared dependencies.**  
   **Plan:** §4 and §8 Phase 5 (`web/package.json`: add `typescript`, `@tanstack/react-query`, `zustand`, `zod`, `openapi-typescript`, `vitest`; gate `npm ci && npm run typecheck && npm test`).  
   **Reality:** `web/package.json` has no TypeScript and no React type packages; `web/package-lock.json` has no `@types/react`, `@types/react-dom`, `typescript`, `@testing-library/react` or `jsdom`. `tsc --noEmit` on `.tsx` files fails without React types even with `allowJs`. `npm ci` fails as soon as `package.json` is changed without a regenerated lockfile, and the plan never says to commit one. Vitest hook tests need a DOM and a renderer, neither of which is in the plan.  
   **Why it matters:** the “green” frontend gate is not achievable as written, and the lockfile omission will break CI.  
   **Fix:** add `typescript`, `@types/react`, `@types/react-dom`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`, `vitest`, and the config files; regenerate and commit `package-lock.json`; specify `jsx`, `moduleResolution: "bundler"`, `types`, `lib`, `include` and a test environment. Also state whether Tailwind/shadcn are actually in scope: §4 says yes, §9 says “keep the current CSS”.

6. **Blocker — the Phase 7 cutover/CI gate cannot pass.**  
   **Plan:** §8 Phase 7 (`stack-migration.md:291-303`: delete `interfaces/api/{server,read,write,downloads,static}.py`, verify `ruff`/`mypy`, keep the `check` job).  
   **Reality:** the `check` job syncs only `--extra dev` (`/.github/workflows/ci.yml:24`) while every new HTTP test imports FastAPI/Starlette from the proposed `server` extra. `tests/unit/interfaces/api/test_ui.py:13` imports `works.interfaces.api.server`, so deleting that module breaks the test suite. Phase 7's gate does not run `pytest` at all.  
   **Why it matters:** the cutover commit will be red in CI and the old tests will fail after the deletion.  
   **Fix:** make CI install `--extra dev --extra server` (or add FastAPI to dev), migrate/delete the legacy HTTP tests as part of the cutover, run `pytest` in the Phase 7 gate, and keep any `interfaces.http` import lazy so `works --help` works without the server extra.

7. **Major — the contract-test strategy cannot prove JSON parity as specified.**  
   **Plan:** §8 Phase 0 and Phase 2 (“calls the legacy server ... writes every GET/POST response”, “assert JSON equality (field order irrelevant, timestamps normalized)”, `stack-migration.md:181-185,220-221`).  
   **Reality:** task detail contains `task.updated_at`, event timestamps, absolute repo paths, run ids, readiness scans and release packets (`src/works/interfaces/api/presenters/tasks/detail.py:127-150`); `_run_index` scans every run; embedded artifact URLs are absolute API paths (`presenters/tasks/artifacts.py:41`); POSTs mutate the demo home and are not replayable in arbitrary order. “Timestamps normalized” is not enough, and there is no seed-home fixture.  
   **Why it matters:** the tests will either be brittle, skipped, or compare a server to itself; the migration loses its main safety net.  
   **Fix:** commit a deterministic seed home (including the fixture repo and flows), define a canonicalizer for timestamps, absolute paths, run ids, task ids, readiness output and URLs, capture GETs and POSTs against isolated copies of that home, and scope “JSON equality” to named fields. Separate the SSE schema from the REST fixture contract.

8. **Major — the Pydantic response models are far smaller than the payload the UI consumes.**  
   **Plan:** §8 Phase 2 (`TaskSummary`, `TaskDetail`, `RunSummary`, `Pipeline`, `ThreadMessage`, `Rail`, `ArtifactDownload`), §5.1 (“detail (story, proof, rail, runs)”).  
   **Reality:** `TaskSummary` must include `risk`, `decision`, `would_block`, `waiting_on`, `title`, `product`, `source`, `updated_at` (`detail.py:23-40`). `TaskDetail` contains `task`, `summary`, `run`, `evidence`, `proof_md`, `timeline`, `pipeline`, `readiness`, `features`, `release`, `delivery`, `deployment`, `confirmation`, `team`, `laix`, `verifier`, `artifacts`, `runs`, `thread`, `rail` (`detail.py:127-150`). The plan lists only a subset, and a strict response model would silently drop fields the UI uses (Story risk, Release deployment/LAIX, Evidence verifier/team, Session rail).  
   **Why it matters:** FastAPI response models filter and coerce; missing fields become client errors, exactly the kind of drift contract tests are supposed to catch.  
   **Fix:** either model every field or mark opaque blobs as `dict[str, Any]`; add a contract test that asserts every key read by `web/src` is present. Include `run` versus `runs` explicitly.

9. **Major — versioning the API breaks URLs embedded in response bodies.**  
   **Plan:** §5.1 (`/api/v1`), §7 (`artifacts`, `presenters` kept), §9 (“generated types ... keep the same user-visible wording”).  
   **Reality:** `_artifact_list` emits `"/api/tasks/{id}/artifacts/..."` (`src/works/interfaces/api/presenters/tasks/artifacts.py:41,58`), and the UI uses that URL for lightbox/downloads. The export links in `web/src/features/evidence/Evidence.jsx:54` are also hard-coded `/api/tasks/...`. A `/api/v1` daemon will return links that 404, and JSON equality tests will fail on these strings.  
   **Why it matters:** the UI’s artifact and export features break even if every route is otherwise correct.  
   **Fix:** emit version-relative URLs (e.g. `/api/v1/...`) from one helper and update the fixtures; or keep the embedded URLs relative to the current prefix and add a test that every returned URL resolves.

10. **Major — the performance targets are inconsistent with the actual read path and the project’s own budget.**  
    **Plan:** §13 (“p95 reads < 150 ms”, memory < 300 MB), Phase 8 (200 tasks, 20 SSE clients), §4 (“SQLite ... unchanged”).  
    **Reality:** `GET /tasks` calls `Queue.list_tasks()` and then `queue.events()` for every task (`read.py:54`, `detail.py:153-157`); `GET /tasks/{id}` calls `_run_index()` over every run and `readiness(Path(task.repo))` on every request (`detail.py:82,135`); the SQLite index/fast path exists (`adapters/queue/index.py`, `fast_read.py`) but the API does not use it. The repository’s existing performance test is 10,000 tasks and `status` under 100 ms (`tests/integration/test_performance.py:16-56`), an order of magnitude harder than the plan’s load test.  
    **Why it matters:** the plan will pass its own small test while failing the product’s documented scale; live SSE polling every 0.6 s over all artifacts makes it worse.  
    **Fix:** switch list/read routes to `TaskIndex`/`fast_read`, cache readiness/release per repo state, split the detail payload, and add a 10,000-task load gate. State whether 200 tasks is a smoke test or the target.

11. **Major — the static/SPA design conflicts with itself and drops the mascot.**  
    **Plan:** §5.2 (unknown routes return JSON 404), §8 Phase 6 (“Static mount: `dist` at `/`, SPA fallback to `index.html`”), §8 Phase 7 (delete `static.py`).  
    **Reality:** `static.py` serves both `dist/` and `/mira.svg` from `src/works/interfaces/ui/static/mira.svg` (`static.py:8-16`); `App.jsx:266` and `Story.jsx:64` request `/mira.svg`. A `StaticFiles(dist)` mount at `/` does not serve that file, so the empty state and Story image 404 after Phase 7. A catch-all SPA fallback mounted at `/` will also swallow unknown `/api/...` paths and return `index.html` 200, contradicting the 404 JSON rule.  
    **Why it matters:** visible UI regression plus a broken error contract.  
    **Fix:** copy `mira.svg` into `web/public/` (so Vite puts it in `dist`), mount `StaticFiles` after API routes, add an explicit `/api` catch-all returning JSON 404, and make the SPA fallback only match non-API paths. Test `/`, `/assets/*`, `/mira.svg`, `/api/v1/nope`, and a deep hash link.

12. **Major — auth design is ambiguous at the two points that matter: token lifetime and Windows permissions.**  
    **Plan:** §5.4 (daemon writes a random token; `works ui` opens `?bootstrap=<one-time-token>`; SPA exchanges it for an HttpOnly cookie; reads need no cookie; CLI uses Bearer), §14.  
    **Reality:** the same “random token” is described as both the one-time bootstrap token and the long-lived CLI Bearer token, but `POST /session` is said to consume it. If it is consumed, the CLI cannot authenticate; if it is not, it is not one-time. There is no cookie value/signing design, no `POST /session` row in the §5.1 table, and no logout/rotation. `.gitignore` ignores only `/.works/settings.json`, so a new `.works/state/http-token`, `daemon.pid` and `daemon.log` would be committable. `chmod(0600)` is not an ACL on Windows. The parser still accepts arbitrary `--host` (`src/works/interfaces/cli/parser/ui.py:12`) while the plan says loopback only, and `POST /session` itself must be exempt from “every mutating request requires a cookie”.  
    **Why it matters:** writes and CLI transport may be mutually exclusive; a token can leak into git or into a shared workspace; the daemon can be bound publicly.  
    **Fix:** separate a persistent `http-token` (0600/ACL, ignored) for CLI Bearer from per-`works ui` short-lived bootstrap tokens; define `POST /session` request/response, cookie name/value, max-age and rotation; validate `--host` and `Host`; add Origin/Sec-Fetch-Site checks; gitignore `.works/state/`; document the Windows ACL implementation; test read-only mode.

13. **Major — job lifecycle, cancellation and crash recovery are underspecified and partly impossible.**  
    **Plan:** §5.5 (“status: queued|running|succeeded|failed”; cancellation “kills the worker thread’s subprocess where possible and records `cancelled`”; max 2 concurrent), §6, §8 Phase 8.  
    **Reality:** the status enum omits `cancelled` although the text uses it. No `CommandRunner` or `SubprocessRunner` exposes cancellation (`src/works/adapters/processes/runner.py:76-163`), and `team_verify` and `_collect` use `subprocess.run` without a handle (`launcher.py:73`, `chat.py:59`). Python cannot kill a thread; a `DELETE /jobs/{id}` cannot stop a run that is inside `Popen.communicate()`. Jobs live in memory only, so a daemon restart loses `running` jobs while the task remains claimed by an `owner` file that is only removed in `Supervisor.run`’s `finally` (`core.py:158,184`, `adapters/queue/claims.py:22`).  
    **Why it matters:** a crashed daemon can leave tasks permanently unclaimable, and cancellation becomes a lie once a git push or model call has started.  
    **Fix:** add a per-job process registry and cooperative cancellation, a persisted job store with startup reconciliation, owner-stale detection (heartbeat or PID + start time), explicit “cannot cancel after side effect X” semantics, and tests for cancel, crash, restart and stale owner.

14. **Major — one supervisor built in the lifespan will not honour settings or per-flow prompts.**  
    **Plan:** §8 Phase 1 (“lifespan that builds the queue and supervisor once”), §5.1 `GET/POST /settings/builder`.  
    **Reality:** `_supervisor()` reads `BuilderSettings` and constructs `LiveHarness`/planner once from argparse (`src/works/interfaces/cli/commands/wiring.py:72-184`); the harness captures provider/model/prompt paths. Saving settings calls `save_builder_settings` (`application/settings.py:124`) but the daemon’s existing supervisor keeps the old harness. A single supervisor also cannot vary the prompt path per flow (`wiring.py:120-124`).  
    **Why it matters:** the Settings screen will appear to save but the next run still uses the old builder; planner modes/critic are similarly stale.  
    **Fix:** extract a `build_supervisor(config)` factory independent of argparse and construct one supervisor per job from the current settings; invalidate/validate active jobs on save; add a test that changes provider/model and observes the next run.

15. **Major — "one worker / one writer" contradicts 2 job workers, background threads and standalone CLI writes.**  
    **Plan:** §2 (“One writer: the daemon owns the queue”), §6 (“Uvicorn runs one worker. One writer ...”), §5.5 (max 2 jobs), §15 (“Double writes ... one daemon”).  
    **Reality:** the daemon proposes 2 job threads plus request threads plus the LiveState watcher; the CLI can still run `works run`, `works deliver`, `works confirm` directly; `approve_plan`/`release` have no per-task lock in `write.py` (the `threading.Lock` only wraps some calls); `Queue` uses FileLocks per operation but `Supervisor` itself is shared.  
    **Why it matters:** “one writer” is not enforced, and two jobs can mutate the same task or run overlapping gates.  
    **Fix:** define the actual concurrency model: job executor with 2 workers, per-task lock in the job registry, one supervisor per job, and a documented/guarded standalone mode (`--standalone` refuses if a daemon owns the home, or uses a distinct home). Add a concurrent-gate test.

16. **Major — SSE event synthesis and replay are not designed.**  
    **Plan:** §5.3 (`queue.changed`, `task.changed`, `run.changed`, `job.changed` with ids; monotonic `id`; `Last-Event-ID`), §6 (broadcaster drains `LiveState`), Phase 4 (ring buffer 200).  
    **Reality:** `LiveState` emits only `{"type":"changed","at":...}` (`src/works/interfaces/api/live.py:70`); it has no task/run/job ids, no job directory, no settings watch, and it polls all queue/run files every 0.6 s. The current UI consumes unnamed messages via `source.onmessage` (`web/src/App.jsx:158-169`); named events require per-event listeners, and an `EventSource` cannot send a POST for `ask/stream`. A global ring of 200 with a counter that resets on restart has no “history lost” signal.  
    **Why it matters:** the new UI cannot invalidate the right cache from a generic “changed”, and a reconnect after 200 events silently misses changes.  
    **Fix:** specify a change-to-event mapper (tail `events.jsonl`, job store, settings), a per-client drop policy, an epoch/resync event when `Last-Event-ID` is older than the ring, and a hook that registers each event name. Add tests for a task change, a run change, a job change, heartbeat and replay-after-gap.

17. **Major — the action→job UX is missing from the frontend plan.**  
    **Plan:** §5.5 (long actions return 202 + job), §18 (Release/Session actions), §8 Phase 5 (hooks include `useJob` but no screen item).  
    **Reality:** `runAction` in `web/src/App.jsx:95-115` assumes a synchronous result and immediately toasts/refreshes; `Release.jsx` calls `deliver`/`confirm` and expects `detail.delivery`/`detail.confirmation` after the call. A 202 job with no polling shows “deliver recorded” but no delivery, and repeated clicks start duplicate jobs.  
    **Why it matters:** every long action in Release and Session will appear broken even if the backend is correct.  
    **Fix:** add an explicit `useAction`/`useJob` state machine (queued/running/succeeded/failed/cancelled), per-action busy/disabled UI, progress/log tail, refresh on completion, error mapping, and a test for deliver/confirm/team-verify/commentary. Define whether `POST /ask/stream` remains the only ask path.

18. **Major — Windows daemon lifecycle, cwd and environment are the largest hidden prerequisite.**  
    **Plan:** §8 Phase 6 (`daemon start|stop|status`, pidfile, log, single-instance lock), §12, §15 (“Windows paths and `claude.exe` — do not change adapter logic”).  
    **Reality:** `create_task` resolves a relative `repo` against `Path.cwd()` (`src/works/interfaces/api/write.py:29-30`); a detached daemon started from another directory will reject or resolve the wrong repository. `readiness` has the same cwd assumption. The chat worker, team launcher and swarm runtime hard-code `C:\Workspace\openjiuwen\agent-core` / `jiuwenswarm` (`application/assistant/runtime.py:19,24`, `application/team/launcher.py:27,63`, `adapters/harness/swarm/runtime.py:18,23`). A detached process does not inherit a shell’s later env changes, and Windows `os.kill(SIGTERM)` is not a graceful uvicorn shutdown; PID reuse can make a stale pidfile point at an unrelated process.  
    **Why it matters:** “works daemon start” can work in a dev shell and fail for every real user; runs can target the wrong repo or lose the model key.  
    **Fix:** write a `daemon.json` with `{pid, host, port, home, started_at, token_path}`; start detached with explicit cwd=`home`, an allow-listed environment snapshot, and log redirection; stop via a health/identity check then a graceful signal/`CTRL_BREAK_EVENT`; resolve relative repos against `home`, not cwd; document `WORKS_AGENT_PYTHON`/`WORKS_AGENT_CORE`/swarm env; add Windows tests.

19. **Major — packaging claims are broader than the wheel content test.**  
    **Plan:** §12 (“Wheel includes `src/works/interfaces/ui/static/dist`”; add a wheel-content test), Phase 7.  
    **Reality:** the runtime also depends on repo-relative `scripts/agent_chat_worker.py`, `scripts/team_verify_worker.py`, `scripts/swarm_adapter.py` and a `flows/` tree (`application/assistant/runtime.py:11`, `team/launcher.py:76`, `swarm/runtime.py:27`, `config/paths.py:21`). None of those are in the proposed wheel test. The Vite `dist` is committed and can be stale; `npm run build` writes into the package tree (`web/vite.config.js:7`), so a CI web build dirties the checkout and a wheel built without the web job ships the old UI.  
    **Why it matters:** an installed `works` can serve the SPA but fail Mira/team/swarm or lack flows; the packaged UI can be older than `web/`.  
    **Fix:** move worker scripts into the package or declare them as package data, include `flows/` (or bootstrap it), test `works ui` + `works ask` + `works team verify` from an installed wheel, and add a CI check that `dist` matches a fresh build (build then `git diff --exit-code`, or build inside the wheel job).

20. **Major — `/metrics` is already the factory metrics endpoint; process metrics would collide.**  
    **Plan:** §5.1 (`GET /metrics`, `/ledger` observability), §13 (“Metrics: request latency, queue depth, active runs, job failures, SSE clients”), Phase 8.  
    **Reality:** `GET /api/metrics` returns `{"metrics": FactoryMetrics}` from `collect(queue, ledger)` (`read.py:66-71`), and the Factory dialog depends on `tasks`, `proved`, `blocked`, `human_touches`, `median_duration_ms`, `tokens`, `usd` (`web/src/features/dialogs/factory.jsx:16-19`). The plan never says whether request/job metrics extend this body, replace it, or get a new path.  
    **Why it matters:** changing the shape breaks the Factory screen and the contract; adding untyped fields silently changes the payload.  
    **Fix:** keep `/metrics` as factory metrics and add `/api/v1/system/metrics` (or an additive, separately typed object) for latency/queue/jobs/SSE; document both.

21. **Major — CLI daemon transport cannot satisfy “same command returns the same JSON in both modes” for jobs.**  
    **Plan:** §2 (CLI attaches or standalone), §8 Phase 6 (“`--standalone` (default for one-shot) and `--daemon` (HTTP + token)”; “same command returns the same JSON”), §5.5 (long actions return 202).  
    **Reality:** `works deliver`/`confirm`/`team verify`/`source` are sync today; through the daemon they are 202 jobs. A CLI that prints the 202 body is not the same JSON as standalone; a CLI that waits needs polling, timeout, cancellation and exit-code mapping. `ask` is streaming. No parser change or plumbing is listed for global `--standalone`/`--daemon`.  
    **Why it matters:** the CLI is declared first-class, but the transport semantics are undefined and the implementation work is hidden.  
    **Fix:** define a `run_job_and_wait` CLI adapter with progress to stderr, JSON result on completion, exit codes from the job result, timeout/cancel behaviour; add tests for each command in both modes; keep streaming `ask` explicit.

22. **Major — the parity checklist is not a specification and omits shipped features.**  
    **Plan:** §18.  
    **Reality:** the UI also has queue grouping and counts (“Needs you / In progress / Done”), the mobile New task button, the empty-state mascot, the Factory metrics/ledger dialog, the Run dialog, the raw-event dialog, the Session rail and plan/decision cards, the conversation/run-log switch, provider availability/credential labels, the planner provider/critic selectors, localStorage persistence keys, the poll fallback, and read-only mode. Evidence is missing policy, risk, decision, residual risk, cost, verifier, team and LAIX, all of which are rendered. Release’s “deploy” item has no endpoint or action in the plan (only the CLI `works deploy`).  
    **Why it matters:** “manual parity pass” will miss features; many are data-bound and will regress silently.  
    **Fix:** turn §18 into a table of screen → component/file → API fields → action/endpoint → test, including read-only and empty states. Add Factory, RunDialog, EventDialog, mobile, mascot and deploy (or remove deploy from the claim).

23. **Major — the estimate is not credible for the stated scope.**  
    **Plan:** §16 (~14–16 days).  
    **Reality:** `web/src` alone is about 6,255 lines across 46 JS/JSX/CSS files, with ~40 components and a 2,700-line CSS system; Phase 5 proposes TS conversion, TanStack Query, Zustand, Zod and possibly Tailwind/shadcn. Phase 3 includes security, job executor, cancellation, nine actions, idempotency, settings and smoke. Phase 6 includes Windows process management. The plan has no contingency, no parallel staffing assumption, and Phase 0/3/5/6 are each underestimated.  
    **Why it matters:** a 2× miss destroys the migration schedule and encourages skipping gates.  
    **Fix:** re-estimate at 25–35 engineer-days with a 20% contingency; split Phase 3 into jobs/security and actions; split Phase 5 into toolchain/contract then screens; treat Phase 6 Windows lifecycle as its own 3–4 day phase.

24. **Major — test/CI mechanics are not implementable as written.**  
    **Plan:** §11 (pytest with `httpx` ASGI; contract tests; SSE fake clock; CI jobs), Phase 1 (`httpx.ASGITransport`), Phase 7 (CI add `web` and `contract`).  
    **Reality:** `httpx.ASGITransport` does not run FastAPI lifespan, so an app whose queue/supervisor are built in lifespan will fail `test_health` unless `asgi-lifespan` or `TestClient` is used. The `web` job has no Python/daemon to produce `openapi.json`; the `contract` job has no server-extra sync. `openapi-typescript` consumes a schema file/URL, but the plan says “CI regenerates” without a dump step. The existing coverage gate is 80% (`pyproject.toml:111`) and no phase gate mentions it.  
    **Why it matters:** the first “green” claim will be false or the tests will be reduced to trivial imports.  
    **Fix:** add `asgi-lifespan` (or use `TestClient`), commit `docs/reference/openapi.json` generated by a Python script, generate TS from that file, make CI `contract`/`web` jobs explicit with both toolchains, and include coverage in the gates.

25. **Major — the error mapping is semantically wrong for configuration and auth failures, and conflicts with the UI’s current error parser.**  
    **Plan:** §5.2 (`ConfigError`/`ValueError` → 400, `HarnessError` → 502, any other → 500), §9 (“map API error codes to the existing toast strings”).  
    **Reality:** `ConfigError` is used for missing model keys, missing agent-core, unready JiuwenSwarm and invalid saved settings (`application/settings.py`, `assistant/runtime.py`, `wiring.py`), not only bad request bodies; 400 tells the user to fix the request. FastAPI/Pydantic validation defaults to 422, not 400. There is no `AuthError`/401/403 mapping. The current client throws `new Error(data.error)` (`web/src/lib/api.js:17`), so the new `{error:{code,message}}` body becomes `[object Object]` in every toast.  
    **Why it matters:** users will get misleading statuses and unreadable errors; monitoring will misclassify server faults as client faults.  
    **Fix:** separate request validation (400/422) from environment/config (409/500/503), add 401/403 and job conflict codes, and update the client to read `error.message` + optional `error.code`; keep a table of code → user wording.

26. **Minor — endpoint/table details are inconsistent or missing.**  
    **Plan:** §5.1 vs Phase 1/6.  
    **Reality:** the table says `GET /health` while Phase 1 implements `GET /api/v1/health`; `POST /session` is described in §5.4 but absent from the table; `GET /api/v1/openapi.json` is only in §12; there is no `HEAD` or `/api/v1` catch-all; `GET /detectors?refresh=` (existing) is omitted; `GET /tasks/{id}/artifacts/{name}` will not match nested artifact paths unless it is `{name:path}`.  
    **Why it matters:** small mismatches produce broken links and ambiguous client generation.  
    **Fix:** make `/api/v1/health` canonical (keep an unversioned alias if `works ui` needs it), add `POST /session`, `GET /openapi.json`, `HEAD`, detector refresh and `{name:path}`; update the OpenAPI source of truth.

27. **Minor — body limits, timeouts and the p95 write target are not designed.**  
    **Plan:** §13 (p95 writes < 300 ms), §14 (64 KB body “as today”), Phase 8 (oversized body test).  
    **Reality:** the legacy limit is a `Content-Length` check in `server.py:108-110`; FastAPI/Starlette accepts chunked bodies with no limit. `POST /sources` performs GitHub/Jira network calls, `POST /readiness` runs commands, and `commentary`/`discussion` can take 180 s; all are currently classified as synchronous.  
    **Why it matters:** the security test and the latency target contradict the action classification.  
    **Fix:** add a streaming body-limit middleware, a per-job timeout policy, and either exclude network/model actions from the p95 target or make them jobs. Test chunked and oversized bodies.

28. **Minor — observability/dependency details contradict the code.**  
    **Plan:** §4 (`structlog`, `watchfiles`), §13 (JSON logs with `request_id`, `task_id`, `run_id`, `job_id`, `duration_ms`), §8 Phase 8.  
    **Reality:** `src/works/config/logging.py` already emits JSON, but its formatter includes only `run_id`, `task_id`, `step`, `duration_ms`, `tokens`, `usd`; it has no `request_id` or `job_id`. `structlog` and `watchfiles` are not in the proposed `server` extra, and `LiveState` remains a polling thread (`live.py:64`), so `watchfiles` is either unused or an undocumented dependency. Uvicorn access logs bypass the formatter.  
    **Why it matters:** the observability claim is not delivered by adding `structlog`; logs and metrics will be split across two formats.  
    **Fix:** reuse `config/logging.py`, add the missing fields and a request-id context, route uvicorn access/error logs through it, and either implement watchfiles or remove it; add dependencies to the extra if used.

29. **Minor — daemon naming, legacy switch and rollback are unresolved.**  
    **Plan:** §7 (`ui.py` starts/attaches the daemon; `--legacy`), §8 Phase 1 (`works daemon` registered in `cli/parser/run.py`), §19 (open: `works daemon` vs `worksd`; keep `WORKS_HTTP=legacy`), §20.  
    **Reality:** `interfaces/cli/parser/run.py` is the `run/wait/wake/dispatch/policy` group, not a daemon module; adding `daemon` there is the wrong grouping. Neither `--legacy` nor `WORKS_HTTP` exists anywhere in the code, and Phase 7 deletes the legacy server, so the “keep legacy for one release” option and the rollback story conflict.  
    **Why it matters:** the rollback plan and parser layout are inconsistent, and a reviewer cannot tell which option is chosen.  
    **Fix:** choose `works daemon` or `worksd`, put it in `cli/parser/daemon.py` and `cli/commands/daemon.py`, and either implement a real `--legacy`/`WORKS_HTTP` switch with tests or remove it and rely on the `pre-fastapi` tag. Close the §19 decisions before Phase 1.

30. **Minor — state paths and workspace bootstrap are not in `WorksPaths`.**  
    **Plan:** §5.4 (`.works/state/http-token`), Phase 6 (`.works/state/daemon.pid`, `daemon.log`), §12 (wheel).  
    **Reality:** `WorksPaths` has `queue`, `runs`, `flows`, `worktrees`, `ledger`, `scenarios` and no state dir (`src/works/config/paths.py:10-48`); `ensure()` creates only queue/runs/worktrees. `settings_path` uses `.works/settings.json` (`application/settings.py:21`). A fresh home therefore has no flows and no state directory.  
    **Why it matters:** daemon startup, token creation and `works ui` on a new home fail or scatter files.  
    **Fix:** add `state_dir`/`settings_dir` to `WorksPaths`, create them in `ensure()`, define flow bootstrapping, and test a fresh `--home` with only `works ui`.

31. **Minor — `mira.svg`, `/app.js` and other mapping details show the plan was not checked against the tree.**  
    **Plan:** §7 (“legacy `/app.js` fallback”), §8 Phase 6 (“no legacy `/app.js`”), §7 (`interfaces/api/static.py` → `StaticFiles`).  
    **Reality:** there is no `/app.js` fallback in `server.py` or `static.py`; `_dist_asset` only serves `index.html` and `assets/` (`static.py:19-30`). Conversely, the real static special case (`/mira.svg`) is not mentioned.  
    **Why it matters:** the deletion checklist removes something that does not exist and omits something that does; reviewers will chase the wrong files.  
    **Fix:** delete the `/app.js` references; add `/mira.svg` and favicon to the static checklist with a test.

32. **Nit — several “parity” items are already broken or misleading today.**  
    **Plan:** §18 (“copy link”, “import duplicate handling”, “Release ... deploy”).  
    **Reality:** Story’s Copy link only calls `onToast("Link copied.")` (`web/src/features/story/Story.jsx:61`); Import reads `result.imported` while the API returns `created` (`web/src/features/dialogs/import.jsx:25`, `write.py:252-256`), so it always says 0 imported; Release has a Deployment card but no deploy action/endpoint, only a message to run the CLI (`Release.jsx:104-114`).  
    **Why it matters:** “parity” would preserve bugs or claim a feature that never existed.  
    **Fix:** define expected behaviour and a test for copy-to-clipboard, import counts and deploy; either add a `POST /actions` deploy job or remove deploy from §18.

## Coverage gaps

UI calls and endpoints not fully addressed by the plan:

- `GET /api/health`, `/api/products`, `/api/detectors` — mapped, but `?refresh=1` and detector network errors are not.
- `GET /api/tasks?limit=200` — mapped, but grouping/counts and 10k-task load are not.
- `GET /api/tasks/{id}` — mapped, but the full payload (`summary`, `run`, `evidence`, `proof_md`, `timeline`, `features`, `release`, `delivery`, `deployment`, `confirmation`, `team`, `laix`, `verifier`, `artifacts`, `thread`, `rail`) is not modeled.
- `GET /api/tasks/{id}/runs` — mapped, but `RunSummary` fields (`files`, `not_tested`, `delivered`, `confirmed`) and duplicate `detail.runs` are not.
- `GET /api/tasks/{id}/export/{kind}` — mapped, but the UI links are hard-coded `/api/tasks/...` and `FileResponse` media types differ from `_content_type`.
- `GET /api/tasks/{id}/artifacts/{name}` — nested artifact paths need `{name:path}`; lightbox/media types are not covered.
- `POST /api/tasks` — mapped, but the `url: "#/task/..."` response and hash-routing compatibility are undecided.
- `POST /api/actions` — mapped, but the plan counts eight instead of nine, misclassifies `commentary`/`discussion`, and does not cover the UI’s `run-readiness` call.
- `POST /api/actions` `deploy` — promised by §18 but absent from the endpoint table and action code.
- `POST /api/readiness` — mapped, but the UI currently calls `POST /api/actions` with `run-readiness`; no UI migration is described.
- `POST /api/sources` — mapped, but GitHub/Jira network calls are not classified as jobs and import counts are already wrong.
- `GET/POST /api/settings/builder` — mapped, but GET is not implemented today, settings are not applied to a live supervisor, and theme/density/poll/repo remain localStorage.
- `GET /api/metrics`, `/api/ledger` — mapped, but `/metrics` is the Factory metrics endpoint, and the new process metrics have no path.
- `GET /api/events` — mapped, but no source for task/run/job ids, no history-gap signal, and no named-event hook.
- `POST /api/ask/stream` — mapped, but the sync generator blocks the loop; the new frontend also needs a streaming-fetch path, not `EventSource`.
- `POST /api/session` — described in §5.4 but missing from the endpoint table and from every phase.
- `GET /api/v1/openapi.json` — only mentioned in §12; no dump/generation/CI step.

UI features not covered by §18:

- Queue grouping (“Needs you / In progress / Done”), counts, state filters, the mobile New task button and the live/write dot semantics.
- Empty-state mascot, Story memory badge, blocked callout, “How we got here” replay, Present mode keyboard handling, and a real Copy link.
- Evidence policy, risk, decision, residual risk, cost, verifier, team, LAIX, run metadata, raw-event dialog and artifact media types.
- Release deployment (no deploy action), LAIX, verifier, raw run dialog and run comparison inputs.
- Session rail, phase cards, plan/decision cards, conversation/run-log switch, review grouping and ask busy/streamed states.
- Settings provider availability/credential labels, planner provider/critic selectors, verifier split, and the local/server split of theme, density, poll and repo.
- Factory metrics/ledger dialog; Palette commands; Help; toasts; keyboard shortcuts; localStorage key migration; polling fallback; read-only mode; `works ui --json/--no-open/--port/--host`.

## Suggested phase changes

- **Phase 0:** split into 0a “fixture home + canonicalizer + baseline capture” and 0b “OpenAPI dump + frontend toolchain/lockfile”. Do not gate on JSON equality until the canonicalizer is specified.
- **Phase 1:** add lifespan shutdown, `asgi-lifespan` (or `TestClient`), lazy `interfaces.http` imports, and a `works --help` test with only the base extra.
- **Phase 2:** add the seed-home fixture and use `TaskIndex`/`fast_read` for list/detail; decide whether `detail.runs` stays or moves to `/runs`; do not put readiness scans in the contract path.
- **Phase 3:** split into 3a “jobs, cancellation, persistence, security/session” and 3b “actions, sources, settings, readiness”; add deploy or remove it; replace the smoke script with a seeded/fake-harness flow; add 2–3 days.
- **Phase 4:** make the SSE change-to-event mapper an artifact, not an implementation detail; add named-event and history-gap tests; bridge the synchronous `ask_mira_stream` through a thread.
- **Phase 5:** split into 5a toolchain/types/generated client and 5b screens; add the missing type/test dependencies and lockfile; decide Tailwind/shadcn versus existing CSS; add per-screen parity tests.
- **Phase 6:** add the daemon state file, detached Windows start/stop, cwd/home and environment propagation, existing-daemon `--write` behaviour, static mascot, and either a scheduler/run endpoint or a corrected gate.
- **Phase 7:** migrate/delete the legacy HTTP tests, update CI to sync `server` and run `pytest`, verify `dist` is fresh, and add a wheel test for scripts/flows/Mira/team.
- **Phase 8:** add a 10,000-task load test, a cancel-with-side-effects test, a daemon-crash/stale-owner test, and a memory test with Playwright/agent-core loaded.

## Top 10 fixes in priority order

1. **Resolve the async execution model:** per-job supervisor + worker thread running `asyncio.run(supervisor.run(...))`; prove a run cannot block SSE or reads.
2. **Decide the run/scheduler contract:** add `POST /runs`/`POST /dispatch` and a scheduler phase, or remove the claim and fix the Phase 6 gate.
3. **Fix the action taxonomy:** enumerate nine actions, move `commentary`/`discussion`/`ask` to jobs, implement `POST /readiness`, and replace the `run-readiness` UI call.
4. **Replace the Phase 3 smoke test** with a deterministic seeded planning/proved/delivered fixture or a full fake-harness run.
5. **Make contract tests real:** seed home, canonicalizer, complete schemas, versioned embedded URLs, and separate SSE tests.
6. **Fix CI and tooling:** `--extra server` in CI, lazy imports, old-test migration, lockfile, TypeScript/React types, Vitest DOM, and an OpenAPI dump/generation step.
7. **Close the auth design:** persistent CLI token vs one-time bootstrap, signed HttpOnly cookie, read-only mode, loopback/host/Origin checks, Windows ACL, and `.works/state/` in `.gitignore`.
8. **Fix static and packaging:** copy `mira.svg` to `web/public`, route API 404 before the SPA fallback, build a fresh `dist`, and package/verify scripts and flows.
9. **Fix scale and events:** use `TaskIndex`/`fast_read`, cache readiness/release, split detail, add a 10k-task test, and design SSE change-to-event/resync.
10. **Re-scope and re-estimate:** 25–35 days, split Phase 3/5/6, expand §18 into a screen/file/API/test table, and make §17’s “done” criteria measurable.
