# Works 2026 modernization plan (v2)

**Status:** revised after a staff-engineer critique of v1  
**Date:** 2026-11-24  
**Scope:** local-first daemon, CLI, web UI, packaging, AI quality and engineering system.  
**Non-goals:** microservices, Redis/Postgres, Kubernetes, multi-tenant SaaS, a cloud control plane.
Works stays one home with one writable daemon.

## 0. What changed after the critique

The v1 plan was directionally right but overstated “new” work, misstated the baseline, undercounted
the type migration, and added platform pieces that do not pay for themselves in a local tool. This
version:

- separates **landing**, **hardening** and **new** work;
- narrows the index to scalar columns and hydrates the visible page from events, avoiding a
  `domain/application` logic leak into `adapters/`;
- moves Windows lifecycle CI and server-side idempotency to Phase 0;
- replaces OTel/Prometheus/SQLite-job-store/release-signing churn with measurable local gaps:
  backup/restore, retention, liveness/readiness, SSE limits, prompt provenance and a mutation gate;
- reconciles the plan with the existing standard in [`plan.md`](plan.md) §6.4, which is stricter
  than v1 in mutation score, circuit breaking, prompt hashes and “no bare threads”;
- fixes the arithmetic: **81 engineer-days + 20% ≈ 97 days**, not 57 days in 8 weeks.

## 1. Baseline: done, in flight, new

| Area | Status | Notes |
|---|---|---|
| FastAPI `/api/v1`, OpenAPI, generated TS client | **done** | `src/works/interfaces/api`, `web/src/api` |
| Daemon lock, pid identity, start/stop/status, Windows launcher fix | **done** | `scripts/smoke_daemon.py` is manual evidence |
| Jobs, cancellation, timeout, late-result protection | **done** | thread pool, child-tree kill |
| Body limits, request IDs, JSON logs, p95 bench with 20 SSE | **done** | 50 tasks / 500 ms gate |
| Remote bind, trusted hosts, auth-on-read, Host/Origin | **done** | `guard.py` pure ASGI |
| Pairing codes, device tokens, revoke | **in flight** | uncommitted; needs rate limit, audit, expiry, Windows ACL |
| Server-side `Idempotency-Key` | **false signal** | client sends it; no route consumes it |
| Windows CI for daemon lifecycle/wheel | **missing** | CI is Ubuntu-only |
| Python 3.13 / 3.14 | **missing / excluded** | `requires-python = ">=3.12,<3.14"`; CI only 3.12 |
| Strict TypeScript across the UI | **partial** | `allowJs`, `checkJs: false`, screens are `.jsx` |
| Playwright E2E / axe | **missing** | jsdom + parity tests only |
| Backup/restore, retention, session TTL, audit log | **missing** | local-first product gaps |
| Mutation gate on new code | **partial** | weekly gate covers three modules only |
| Makefile, pre-commit, changelog, contributor guide | **done** | use them; don’t re-plan them |
| Weekly `pip-audit` / Bandit supply chain | **done** | `.github/workflows/supply-chain.yml` |

## 2. Reconcile with the engineering standard

[`docs/design/plan.md`](plan.md) §6.4 already requires, among others:

- mutation score ≥70% on core (`queue/`, `policy/`, `verify/`);
- a provider circuit breaker after repeated failures;
- prompt hash recorded in the run/proof;
- structured JSON-only agent output;
- “async for I/O; no bare threads”.

The current job executor uses threads. This plan therefore includes **either** an approved ADR
exception for the bounded job pool **or** a migration to structured `asyncio` tasks. Do not ship two
design documents that disagree. The mutation gate stays and expands to the new index/job code.

## 3. Workstreams

Estimates are engineer-days for one senior engineer; add 20% contingency. Every item names the
failure it prevents and the proof that detects it.

### M0 — Land and harden the in-flight work (6 days)

**Prevents:** a “secure remote” story that is prose, not code; duplicate side effects from retries;
the primary Windows lifecycle path going untested.

- [x] **M0.1** Review and land pairing with: device expiry/idle expiry, an append-only security audit
  log (pair start/success/failure, revoke, rotate, auth failure; no secrets), rate limits on
  `/pair`, `/session` and `/admin/*`, and a real Windows ACL for `http-token`/`devices.json`
  (or an explicit refusal to run a remote bind on a home without a private ACL).
  *Proof:* non-loopback `Host`/`Origin` E2E; 20 failed attempts → `429` + `Retry-After`; audit
  assertions; Windows ACL test.
- [x] **M0.2** Implement server-side `Idempotency-Key` replay for side-effecting actions
  (`release`, `deliver`, `confirm`, `deploy`, `team-verify`, `runs`, `dispatch`) keyed by
  `(key, route, body hash)`; return the prior result on replay and `409` on mismatch. Do **not**
  apply it to `/pair`; `POST /tasks` is already idempotent by deterministic task id.
  *Proof:* replay returns the same job/result; a changed body returns `409`; no duplicate
  delivery/comment/deploy call in the fake provider.
- [x] **M0.3** Add a `windows-latest` CI job for `works daemon start/status/stop`, the detached
  launcher/pid identity, `CTRL_BREAK_EVENT`, wheel install and `scripts/smoke_daemon.py` (short
  mode). *Proof:* the job is required and green; it fails if the launcher-pid regression returns.
- [x] **M0.4** Add Python 3.13 to the CI matrix; keep 3.14 a decision after the dependency cap is
  reviewed. *Proof:* 3.13 check job green.
- [x] **M0.5** `prompt_sha256` is recorded in `run.json` and printed in `evidence.md`;
  `tests/integration/test_loop.py` asserts the same 64-character hash in both.
- [x] **M0.6** Fix docs contradictions: remote pairing wording, CONTRIBUTING Playwright claims,
  Tailwind/shadcn decision in `plan.md` vs `stack-migration.md`. *Proof:* link/text check in CI.

### M1 — End-to-end type safety (11 days)

**Prevents:** untyped API payloads and UI props silently diverging from the contract.  
**Proof:** strict `tsc`, mypy flags, ESLint and a grep gate.

- [x] **M1.1** `py.typed` ships and mypy runs `--strict`. A ratchet
  (`scripts/check_typing_ratchet.py`) runs mypy with `--disallow-any-explicit --warn-return-any`
  against `docs/reference/typing-baseline.json` (317 errors in 93 files): no file and no total may
  grow, and new files start at zero. Removing every boundary `Any` in one change is deliberately not
  done; the baseline only shrinks. No second type checker.
- [x] **M1.2a** Queue, Story, Evidence and Release are typed `.tsx`; `tsc`, Vitest and the bundle
  are green.
- [x] **M1.2b** Session, Settings, `app/*`, dialogs, `ui/*` and every test are typed `.tsx`; there is
  **no `.jsx` under `web/src`**. `tsc`, Vitest (35 tests) and the bundle are green; helpers such as
  `format.js`/`options.js` stay JS behind typed boundaries until M1.3.
- [x] **M1.3** `allowJs: false` with every helper (`format`, `copy`, `route-geometry`, `session/model`,
  `settings/options`, `settings/payload`) converted to typed `.ts`, and `vitest.setup.ts` typechecked;
  only `vite.config.js` stays JS because Vite loads it before TypeScript. `tsc`, Vitest and the bundle
  are green. The committed `dist` gate stays on.
- [x] **M1.4** Zod contracts in `web/src/api/schemas.ts` validate tasks, task detail, health, jobs and
  settings; a mismatch is `ApiError` 502 `bad_response` naming the field. `zod` moved to runtime
  dependencies (the bundle grew ~26 KB minified).
- [x] **M1.5** ESLint 9 flat config with `typescript-eslint`, `react-hooks` and `jsx-a11y`, wired into
  CI (`npm run lint`). The first run fixed a conditional `useState`, four unassociated form labels,
  a click-only milestone (now a keyboard-operable button) and evidence media without a captions
  exception; 7 advisory warnings remain, 0 errors.
- [x] **M1.6** CI greps `web/src` (excluding `src/test/` raw-JSON fixtures) for `: any`, `as any`,
  `@ts-ignore` and `@ts-expect-error` and fails on any hit; every exported component has an explicit
  props type.
- [x] **M1.7** `CONTRIBUTING.md` documents the typed-component pattern, the single narrowing point,
  the grep gate and the Zod boundary contract.

### M2 — Read API at 10k tasks (5 days)

**Prevents:** O(N) scanning of task and event files on every queue request.  
**Proof:** 10k/20-SSE benchmark and an index/file parity test.

- [x] **M2.1** Extend `TaskIndex` with **scalar** columns only: `product`, `title`, `kind`,
  `updated_at`, `waiting_on`. Keep `risk`, `decision`, `would_block` out of SQLite; they stay
  event-derived.
- [x] **M2.2** Add `TaskIndex.list_recent(limit)`; `GET /tasks` takes the page ids from the index and
  hydrates only those tasks/events through the existing presenter. No adapter imports from
  `interfaces/api`.
- [x] **M2.3** Schema version + rebuild on mismatch + corrupt-index fallback + a rebuild time
  budget. *Proof:* corrupted index and old schema tests.
- [x] **M2.4** Add an index/file parity test on a 500-task seeded home: every `_task_summary` field
  is deep-equal between the two paths.
- [x] **M2.5** Add the 10k benchmark: `scripts/bench_api.py --tasks 10000` must seed through
  `TaskIndex.replace`, not 10k fsync submissions; 3 runs, median p95; fail above 250 ms **and**
  above 120% of the `main` baseline for two consecutive runs.
- [x] **M2.6** ADR 018 makes the committed schema the current contract and
  `docs/reference/openapi.baseline.json` the released one; CI fails on a removed operation,
  parameter, schema, property, type change or a required-flag flip. Additive changes pass.
- [x] **M2.7** **Drop** cursor pagination and ETag for now; revisit only if server-side search
  appears.

### M3 — Browser E2E and accessibility (8 days)

**Prevents:** UI/daemon integration regressions that jsdom cannot see.  
**Proof:** Playwright against a real seeded daemon + axe.

- [x] **M3.1** Playwright fixture starts/stops a real `works daemon start --write`, resets a temp
  home, and exposes traces/video on failure.
- [x] **M3.2** Queue → Story → Evidence → Release, Settings pairing, add-context, new task (mobile
  composer), revoke and read-only mode are covered by required journeys. `web/e2e/opt-in.spec.ts` adds
  the two journeys that need a secret: a real GitHub issue becomes a tracker task (`WORKS_E2E_GITHUB=1`,
  uses `gh auth token`) and Ask Mira streams an SSE answer (`WORKS_E2E_ASK=1`, needs a model key).
  Both skip in CI and were proven locally: import passed against issue #1 of the demo repository, and
  the ask stream ended with `done` and no `error`.
- [x] **M3.3** `@axe-core/playwright` runs on Queue, Story, Evidence, Release, Session and Settings in
  the E2E job; serious/critical violations fail the build. It already found and forced two fixes:
  low-contrast muted text in the warm palette and a scrollable route that was not keyboard-focusable.
- [x] **M3.4** `web/e2e/visual.spec.ts` compares Story/Evidence/Release in light and dark, but only
  with `WORKS_VISUAL=1`; baselines stay local because they are platform-specific. No mobile-web pass.
- [x] **M3.5** E2E job is a required CI check with a 25-minute budget.

### M4 — Remote and device trust, after M0 (4 days)

**Prevents:** a LAN bind that leaks reads or cannot revoke a lost phone.  
**Proof:** non-loopback pairing/revoke E2E and a threat-model ADR that maps to tests.

- [x] **M4.1** Settings/CLI device management: list, last seen, revoke, rotate all. (Pairing itself
  lands in M0; this is the surface around it.)
- [x] **M4.2** Security headers: CSP compatible with Vite assets/SSE, `X-Content-Type-Options`,
  `Referrer-Policy`, `Permissions-Policy`.
- [x] **M4.3** Threat model: trusted hosts, auth-on-read, pairing, token theft/lost device, replay,
  LAN MITM, `chmod` on Windows. Record it in an ADR.
- [x] **M4.4** `npm audit --omit=dev` (pip-audit already runs weekly); exceptions need owner +
  expiry.
- [x] **M4.5** Revisit `0.0.0.0` cleartext guidance: default remote demo uses a tunnel or TLS.

### M5 — Observability, liveness and SSE limits (3 days)

**Prevents:** a slow run that cannot be explained; `/health` coupled to model SDK state; a stalled
SSE reader wedging the daemon.  
**Proof:** trace-id log schema, JSON metrics, liveness/readiness tests, slow-consumer test.

- [x] **M5.1** Add `trace_id` to `Job.as_dict()` and job start/finish logs alongside
  `request_id`/`job_id`; a log-schema test enforces the fields.
- [x] **M5.2** Split `/health/live` (cheap) from `/health/ready` (builder/provider diagnostics);
  keep `/health` compatible for now. Remove health from the p95 gate until split.
- [x] **M5.3** Extend the existing JSON `/metrics` (or add one if absent) with named counters for job
  outcomes, queue depth, SSE clients and p95 buckets; **no Prometheus dependency**.
- [x] **M5.4** Add a max SSE client count and a slow-consumer policy with a test that a non-reading
  client cannot wedge the event loop or exhaust threads.
- [x] **M5.5** `works doctor --bundle`: daemon.json, jobs, logs, versions, index health, disk state;
  a redaction test proves no token/cookie/key is included.
- [x] **M5.6** Decided: no Prometheus text and no SLO dashboards. JSON metrics in `/api/v1/ops/metrics`
  plus the OTel spans cover one home; a collector would be a second process to operate.
- [x] **M5.7** Instrumented by default through the OpenTelemetry API; `WORKS_OTEL=1` installs the SDK
  with a console or OTLP/HTTP exporter (`WORKS_OTEL_EXPORTER=none` drops spans for measurement). Spans
  cover HTTP → job → subprocess and the trace id lands in the job record and logs. **Proof:** a full
  console trace without a collector; p95 78.45 → 78.68 ms (+0.3%) on the 10k bench.

### M6 — AI quality, prompts and invariants (14 days)

**Prevents:** silent prompt/model regressions and “advice” that can change a gate.  
**Proof:** a recorded eval set with denominators/thresholds, prompt hash in proof, hostile-model
invariants.

- [x] **M6.1** `flows/prompts.lock.json` lists every shipped prompt with SHA-256, owner and
  changelog; `scripts/check_prompts.py` gates it in `make check` and CI, and a run records the same
  hash as `prompt_sha256` in the proof.
- [x] **M6.2** `evals/` holds 30 planner cases, 20 ask Q/A with required citations and 12 injection
  cases; `scripts/run_evals.py` enforces 100/90/100% thresholds and a 2-point regression delta
  against `evals/baseline.json`, and runs on every push without calling a model.
- [x] **M6.3** `tests/integration/test_hostile_model.py`: a model that claims `PLAN APPROVED`,
  `RELEASE APPROVED` or its own review opens no gate, cannot release a proved task, and cannot turn a
  failed holdout into an allow; invalid or patch-less traces fail closed. Path policy already decides
  paths (`test_a_check_edit_is_refused_for_a_normal_fix`).
- [x] **M6.4** Per-run tokens/usd/wall limits were already enforced; a daily ceiling
  (`WORKS_DAILY_USD`) sums today's ledger, is checked before the run and before the verifier spends,
  and turns into `budget_exceeded` on a `blocked` task — including a zero-token record when the day
  is already over budget.
- [x] **M6.5** Evidence carries `model_calls` (stage, provider, model, adapter version, tokens, usd)
  for plan, build and verify, rendered as a table in `evidence.md` and bound into the proof hash.
- [x] **M6.6** Decided: no cross-provider fallback. Silently switching models changes cost and quality
  behind a release gate; a failed provider stays a visible configuration error.

### M7 — Reliability, backup and data lifecycle (6 days)

**Prevents:** lost evidence, unbounded job growth, duplicate side effects, ambiguous crash state.  
**Proof:** crash matrix on Windows/Linux, restore test, retention test, disk check.

- [x] **M7.1** Jobs record `heartbeat_at`, `pid`, `daemon_id` (refreshed every 5s while queued or
  running); a bounded queue (`WORKS_MAX_PENDING_JOBS`, default 64) answers `503` with
  `Retry-After: 5`, and a per-task conflict stays `409`. JSON job files are kept; no SQLite yet.
- [x] **M7.2** `tests/integration/test_crash_matrix.py` covers 30 persisted-job points (five statuses ×
  valid/truncated/empty/unknown-field/non-object) plus a leftover `atomic_write` temp file, an abrupt
  `os._exit` and an externally killed process (`TerminateProcess`/`SIGKILL`). Each asserts the terminal
  state, the readable restart explanation, the released task owner and idempotent re-reconcile.
  **Process tree:** on Windows each command runs in a Job Object with `KILL_ON_JOB_CLOSE`
  (`tests/unit/adapters/processes/test_job.py`); on Linux `PR_SET_PDEATHSIG` kills the command with the
  daemon even after `SIGKILL` (`tests/unit/adapters/processes/test_orphan.py`). **Exactly-once:** crash
  tests in `tests/unit/application/delivery/test_deliver.py` kill the delivery after the pull request was
  opened and before the record was written, then prove a retry creates no second PR or comment and one
  `delivery.finished` event. Deploy writes a `running` record before the command starts and refuses to
  repeat an interrupted command without `--force` (`test_deploy.py`).
- [x] **M7.3** `works backup`/`works restore`: a home archive (events, runs, ledger, settings) and a
  restore test that preserves evidence and task state.
- [x] **M7.4** Retention: prune terminal jobs while keeping a summary; compact/rotate per-task event
  logs only with an explicit policy; `works doctor` reports disk use; index rebuild has a budget.
- [x] **M7.5** Killed runs are **not** auto-resumed: `reconcile()` marks them failed and releases the
  owner. At-least-once delivery, phase idempotency and the operator recovery path are documented in
  `docs/reference/reliability.md` and the runbook.

### M8 — Runtime matrix and supply chain (4 days)

**Prevents:** unsupported Python/Node surprises and unverifiable dependencies.  
**Proof:** 3.13 CI, Renovate, SBOM, `npm audit`, clean-venv wheel smoke.

- [x] **M8.1** 3.13 is in the matrix (M0.4). 3.14 stays out: `openjiuwen` caps at `<3.14`, so the
  daemon cannot honestly claim support until the provider does (recorded in supply-chain.md).
- [x] **M8.2** Renovate (better than Dependabot for `uv`) for Python and npm, grouped updates.
- [x] **M8.3** The `wheel` job builds a CycloneDX SBOM, writes `SHA256SUMS` for the wheel and the
  SBOM, and uploads both; `pip-audit`, `npm audit --omit=dev` and gitleaks gate the build. The `osv`
  job scans `uv.lock` and `web/package-lock.json` on push and weekly (run 45596833850 is green); the
  only findings are filelock advisories blocked by openjiuwen's `<4` pin, recorded with an expiry in
  `osv-scanner.toml` and explained in `docs/reference/supply-chain.md`.
- [x] **M8.4** The `clean-install` CI job downloads the built wheel, exports `uv.lock` as hashed
  requirements, installs them with `pip install --require-hashes` into a clean Python 3.13 venv,
  installs the wheel with `--no-deps`, then runs `works doctor --json` and the daemon
  `start`/`status`/`stop` cycle on a fresh home.
- [x] **M8.5** `docs/guides/runbook.md` documents Task Scheduler and NSSM with a start/health/stop
  verification; the Windows CI job's `smoke_daemon.py` covers start, kill and restart. No MSI.
- [x] **M8.6** `docs/reference/supply-chain.md` records the deferrals (Sigstore, reproducible builds, MSI,
  OSV, Python 3.14) and the reason for each.

### M9 — Developer experience, mutation and docs (2 days)

**Prevents:** “works on my machine” checks and contradictory docs.  
**Proof:** Makefile targets, mutation gate, docs link check.

- [x] **M9.1** Extend the existing `Makefile` (not `just`) with `e2e`, `wheel`, `bench`; keep
  `check`/`security`; pre-commit already exists.
- [~] **M9.2** `only_mutate` already lists `queue/index.py` and `api/jobs.py`; a weekly `mutation.yml`
  runs mutmut on Linux and enforces `scripts/mutation_gate.py` at 70%. **Measured (run 45596860746):**
  64.9% killed — 720 killed, 388 survived, 1 timeout of 1109. Survivors cluster in `policy.py`
  (`normalize_path`, `is_unsafe`, `_directory`, `check_paths`, `_unquote`, `paths_from_patch`) and one
  in `state.py`; edge-case tests for those branches were added, and the gate needs ~57 more kills.
  **Proof pending:** a green run at or above 70%.
- [x] **M9.3** `scripts/check_docs_links.py` gates 56 files in CI, the contributor guide covers typed
  components, the async boundary and the renderer, and M0.6 fixed the contradictions. No MkDocs.
- [x] **M9.4** ADR 018 plus `scripts/check_api_compat.py` and `make api-compat`; the web job still
  regenerates the TypeScript client and fails if the committed output drifts.

### M10 - Async, React platform and renderer decisions (6 days)

**Prevents:** thread-pool starvation hidden behind "async-first" slogans; unmeasured compiler/RSC
migration.

- [x] **M10.1** All 33 operations are classified in `src/works/interfaces/api/route_classes.py`
  (async-safe / blocking / subprocess / sse) with a note; `scripts/dump_route_classes.py` renders the
  table in `docs/reference/http-api.md` and CI fails when a route is unclassified or the table is
  stale.
- [x] **M10.2** Measured with `scripts/bench_api.py`: 10k tasks, 20 SSE streams, 300 reads, p95
  78 ms. The hot read path (`/tasks`) is index-backed and already runs in FastAPI's thread pool, so no
  route was converted; blocking git/subprocess routes stay sync by design.
- [x] **M10.3** ADR 019 keeps one bounded `ThreadPoolExecutor` (2 workers, 64 queued) as the documented
  exception to `plan.md` §6.4; the 503 backpressure path and the crash matrix cover it.
- [x] **M10.4** React Compiler is opt-in (`WORKS_REACT_COMPILER=1`). `scripts/measure_web.py` builds
  both ways and `web/e2e/perf.spec.ts` measures the first queue render plus console errors; a growth
  over 5% fails the script. Measured: bundle **+6.33%** (JS +7.8%), build ~68% slower, render
  difference within noise (median 609 ms plain vs 674 ms compiler), so it stays off by default
  (ADR 021).
- [x] **M10.5** ADR 020 rejects RSC/Next.js for the local SPA: no SSR/SEO/server-action requirement,
  and a Node runtime next to the Python daemon would double the install.
- [x] **M10.6** `CONTRIBUTING.md` documents the route classes, the single executor and the RSC
  rejection; the ADR index lists 019 and 020.

### M11 — Signal intake 2026 (stage 1, complete)

**Prevents:** a signal that is just a title, arrivals that are polled instead of pushed, and a queue
where the same problem appears five times.

- [x] **M11.1** `Source` carries severity, labels, links, author, channel, `reproduction_hint`,
  `received_at` and an explicit `dedupe_key`; the queue dedupes on `dedupe_key or ref`, and old tasks
  load unchanged.
- [x] **M11.2** `POST /api/v1/hooks/{source}` verifies HMAC over the raw body, rejects a replayed
  delivery id, applies a per-source rate limit (`429`), writes an audit line and metrics, and returns
  `202` only when a task was created. A missing secret is `503`; a bad signature is `401`.
- [x] **M11.3** `python -m works.mcp_server` speaks MCP over stdio with `submit_signal`, `list_tasks`,
  `get_task`, `get_evidence` and `get_release_packet`. There is no gate or release tool; a test fails
  if one appears.
- [x] **M11.4** `GET /api/v1/inbox` groups tasks by a normalised title; `POST /tasks/{id}/merge`
  records `task.merged` and blocks the duplicate; the Queue sidebar shows possible duplicates with a
  Merge button; `POST /inbox/mute` disables a source.
- [x] **M11.5** `.works/sources.json` is the source registry (enabled, product, repo, secret env,
  limit); `works sources list|enable|disable` and `GET /api/v1/sources` expose it with metrics.
- [x] **M11.6** The reproduction hint is stored on the task, copied into evidence and rendered in
  `evidence.md`; stage 2 sees it as advice and never executes it blindly.

### M12 ? Reproduce 2026 (stage 2, complete)

**Prevents:** a reproduction that depends on whatever happens to be cloned and installed on the
laptop, and a "bug" that is really a missing dependency or a flaky test.

- [x] **M12.1** A task can name `repo_url` and `repo_ref` (branch, tag, SHA, `pull/<n>`); managed
  clones live under `<home>/repos/<slug>`, fetch instead of recloning, resolve the ref or fail with a
  configuration error, and support an offline cache (`works reproduce checkout`).
- [x] **M12.2** `works reproduce detect` chooses `.works/reproduce.yaml`, then a narrowed signal, then
  the ecosystem manifest (Python, Node, Go, Rust, Java) and records why. The proof names the source.
- [x] **M12.3** `works reproduce prepare` builds a per-repository environment (venv + requirements, or
  `npm ci`/`npm install`), records the runtime and lockfile fingerprint, and never installs silently
  during a run.
- [x] **M12.4** A failing test node or quoted command in the report narrows the check; free text does
  not invent one.
- [x] **M12.5** A failed reproduction is retried once: a flaky result stops as `flaky_test`, a missing
  module or command stops as `config_error`, and a check that passes is `not_reproducible`.
- [x] **M12.6** Evidence records the reproduction command, its source, attempts, stability and
  environment; `evidence.md` renders a **Reproduce** section.
- [x] **M12.7** The Evidence page has a **How to reproduce** card (command, source, attempts,
  stability, environment, reporter hint) and a field that saves a person's command through
  `POST /tasks/{id}/reproduction`.

### M13 ? Plan 2026 (stage 3, complete)

**Prevents:** a "plan" that is prose, a must-pass set nobody can trace, and approvals that survive an
edit.

- [x] **M13.1** Every step needs a title and `done_when`; preflight checks that commands exist and
  scenario scripts are present without running anything.
- [x] **M13.2** The report's paths are mapped to covering tests (`planning/impact.py`): impact lines
  join verification and uncovered paths are recorded in the plan notes.
- [x] **M13.3** `PlanStore.diff()` renders `+ / - / ~` between the last two versions; every draft is an
  immutable version with its own hash.
- [x] **M13.4** The linter rejects missing acceptance and unavailable commands, and a critic score
  below 0.50 blocks the plan; a model proposal without `done_when` inherits it from the skeleton.
- [x] **M13.5** Plan estimates over the task budget are a lint error before the gate, and evidence
  records the estimate beside the actual usage.
- [x] **M13.6** A person can rework steps in the Story plan card (edit intent/done_when, add or remove
  a step, leave a comment) for the nodes the plan already covers; saving creates a new draft version,
  supersedes the old approval and requires a fresh gate decision.
- [x] **M13.7** The same context produces the same plan and hash (test), and `docs/reference/planning.md`
  documents modes, impact, versions and editing.

### M14 ? Plan gate 2026 (stage 4, complete)

**Prevents:** an approval that does not say who decided, an agent opening a gate, and an approval
that survives an edit or a week of waiting.

- [x] **M14.1** The Story gate card shows the plan's checks, the reviewer and score, the budget
  estimate, the risk, the impact lines and the version diff next to the decision buttons.
- [x] **M14.2** A gate decision is `approved`, `changes_requested` (comment required, task stays in
  planning) or `rejected` (reason required, task blocked).
- [x] **M14.3** Identity is a name plus a device; agent/harness/model/builder identities are refused
  server-side; `WORKS_REQUIRE_QUORUM=1` needs two distinct person/device pairs (ADR 022).
- [x] **M14.4** Approvals expire after `WORKS_APPROVAL_TTL_HOURS` (default 168); the builder refuses
  an expired or hash-mismatched approval with `needs_plan_approval`.
- [x] **M14.5** `gate.decided` is an append-only audit record with decision, by, device, actor kind,
  comment, plan id/hash/version, commit, checks, expiry and the quorum flag.
- [x] **M14.6** `GET /inbox` lists planning tasks with a drafted plan, their waiting time and an
  overdue flag (`WORKS_GATE_REMINDER_HOURS`, default 24); the Queue shows them under Waiting for you.
- [x] **M14.7** Nine unit tests cover the three outcomes, agent refusal, stale hash, expiry, quorum
  and the non-planning refusal; `docs/reference/gates.md` and ADR 022 record the semantics.

### M15 ? Build 2026 (stage 5, in progress)

**Prevents:** an engine that spends past the daily ceiling, an invisible turn, and a failure with no
next step.

- [x] **M15.1** The daily ceiling is checked before the engine starts, not only after the turn; the
  per-run tokens/USD/wall checks stay after it.
- [x] **M15.2** `build.started`/`build.finished` events bracket the turn, and a file outside the
  plan's named write scope is a `plan.deviation` (tested).
- [x] **M15.3** Conformance tests for the harness contract: provider/model/version/harness, costs,
  stop handling and the abstain path.
- [x] **M15.4** The run exposes the turn's progress and Cancel kills the whole tree (Job Object /
  `PR_SET_PDEATHSIG`); this pass adds the events around the turn.
- [x] **M15.5** `transcript.json` records model, provider, adapter version, prompt hash, cost, notes
  and trace as an evidence artifact; `evidence.md` adds a typed **Next step** line.
- [x] **M15.6** A bounded repair loop: `repair.attempts` (capped at 3, default 1) allows an extra
  builder turn only for a failing test/preview or verdict; each retry resets the worktree to the
  approved base, `build.retry` records the reason and evidence records the attempts (ADR 023).
- [ ] **M15.7** Network isolation for build commands (needs an OS sandbox; paths and commands are
  already constrained, the network claim is not made).

### M16 ? Check 2026 (stage 6, in progress)

**Prevents:** testing a different scenario than the one approved, blaming a change for a pre-existing
failure, and a high-risk self-review passing as independent.

- [x] **M16.1** A base-vs-candidate run (`WORKS_DIFFERENTIAL=1`) records the baseline exit and output
  hash; a matching pre-existing failure is named as such instead of being blamed on the change.
- [x] **M16.2** A plan records `scenario_sha` over the scenario scripts; if a script changes after
  approval the run stops with `policy_violation`.
- [x] **M16.3** Evidence lists the checks that were skipped because the flow turned them off
  (`skipped_checks`); impacted tests come from the plan's impact lines.
- [x] **M16.4** `WORKS_REQUIRE_SPLIT_REVIEW=1` refuses a high-risk self-review (same provider and
  credential); low-risk work may share them.
- [x] **M16.5** `WORKS_REPEAT_SCENARIOS=2|3` repeats each scenario; a mixed result stops the run as
  `flaky_test` with the unstable ids, never as allow or block.
- [x] **M16.6** Pre-existing failures, missing dependencies, flakes and verdict failures have typed
  reasons and a Next step in evidence.
- [x] **M16.7** Evidence and the Proof page show the base-commit check; a **Re-check** button on a
  released task re-runs confirmation without a new build.

### M17 ? Proof 2026 (stage 7, complete)

**Prevents:** a page that only looks provable, an event log nobody can check, and a secret copied into
a transcript.

- [x] **M17.1** `works proof verify <run>` recomputes the diff hash, the proof fingerprint, every
  artifact hash and the event root; a tampered page fails with the check named.
- [x] **M17.2** `event_root` is a rolling hash over the run's events up to `event_seq`; removing or
  editing an event is detected.
- [x] **M17.3** The full diff stays in `evidence.json`; the markdown truncates it with a visible note,
  and binary/rename lines are preserved.
- [x] **M17.4** Command tails and the builder transcript are scanned for credential shapes and
  redacted, with the count recorded on the page.
- [x] **M17.5** The page records Python version, platform, adapter version and schema; old pages load
  with defaults.
- [x] **M17.6** Schema fields are additive and a page without them still validates; `docs/reference/proof.md`
  describes the contract.
- [x] **M17.7** `works proof export` writes a tarball with a hash manifest, and `works proof diff`
  reports verdict, risk, cost, changed files and fingerprint movement.

### M18 ? Release gate 2026 (stage 8, complete)

**Prevents:** a release packet that cannot show its proof still verifies, an agent shipping code, and
an approval that outlives the proof.

- [x] **M18.1** The packet carries risk, owners, residual `not_tested`, verdict/challenge, tokens/USD,
  plan estimate, `proof_verified`, `delivery_configured` and rollback; the proof is re-verified.
- [x] **M18.2** A release decision is approved, changes_requested (comment required, stays proved) or
  rejected (reason required, blocked); the UI exposes all three.
- [x] **M18.3** A named person on a device is required; agent/harness identities are refused;
  `WORKS_REQUIRE_OWNER_APPROVAL=1` requires a risk owner for high risk and `WORKS_REQUIRE_QUORUM=1`
  needs two distinct person/device pairs.
- [x] **M18.4** Approvals expire after `WORKS_RELEASE_TTL_HOURS` (default 72) and a new proof or commit
  makes them stale; delivery refuses an expired release.
- [x] **M18.5** Blockers are typed (`proof_mismatch`, `must_pass_failed`, `stale_release`, ?) and
  listed in both `blockers` and `blocker_codes`.
- [x] **M18.6** The release event is append-only with the packet hash, device, comment, commit, proof
  hash, expiry and quorum flag, mirrored into `release.json`.
- [x] **M18.7** The Release page shows the packet and offers Approve/Hold/Reject with a comment;
  delivery and confirmation keep their visible status on the same page.

### M19 ? Deliver 2026 (stage 9, complete)

**Prevents:** shipping a commit that is not the approved one, a push before the token is known good,
and a partial delivery that looks complete.

- [x] **M19.1** Preflight checks that the delivered commit descends from the approved base and that the
  proof still matches; force-push and merge are never used.
- [x] **M19.2** The change request body carries the proof summary, verdict, risk, passed/failed check
  count and `not_tested`, not just a link.
- [x] **M19.3** A step journal (commit, branch, preflight, push, request, comment) is written as the
  delivery progresses and a retry continues from the recorded state; `completed` is only set at the
  end, so a partial record is not reused as finished.
- [x] **M19.4** A forge without a token is refused before the push; the failure and step are recorded.
- [x] **M19.5** Markers and the recorded commit/provider/tracker keep retries idempotent; a changed
  provider is a new delivery, not a silent reuse.
- [x] **M19.6** The journal records the failing step and message; a partial delivery stays visible.
- [x] **M19.7** The Release page lists the delivery steps; dry-run, missing token and crash recovery
  are covered by API tests.

## 4. Sequencing and gates

### Phase 0 — Land the safety floor (week 1)

M0.

**Gate 0 (local met; CI pending):** pairing with rate limit/audit/expiry/ACL; idempotent replay
tested; Windows and 3.13 jobs added; docs contradictions fixed. The first CI run is the gate.

### Phase 1 — Types and the queue (weeks 2–4)

M1 + M2. Queue/Story typing first, then the index schema derived from the typed UI.

**Gate 1:** strict `tsc`/ESLint/mypy; 10k `/tasks` p95 <250 ms with 20 SSE (median of 3, also ≤120%
of `main`); index/file parity; no `.jsx` under `features/`.

### Phase 2 — Browser and phone (weeks 5–6)

M3 + M4.

**Gate 2:** Playwright critical flows + axe; pairing/revoke from a non-loopback host; CSP and
security headers; threat-model ADR with mapped tests.

### Phase 3 — Operability (weeks 7–8)

M5 + M7.

**Gate 3:** trace id in every job/log/metrics; liveness/readiness split; slow-consumer test; 30 crash
points on Windows+Linux; backup/restore and retention tests.

### Phase 4 — AI, platform and release (weeks 9–13)

M6 + M8 + M9 + M10.

**Gate 4:** eval thresholds with denominators; hostile-model invariants; 3.13 wheel smoke; SBOM;
mutation ≥70%; docs link check; async route audit + measured hot-path migration; React Compiler
decision; RSC ADR; OTel no-op trace and <5% overhead.

### Effort

M0 6 + M1 11 + M2 5 + M3 8 + M4 4 + M5 4 + M6 14 + M7 6 + M8 4 + M9 2 + M10 6 + M11 12 + M12 14 =
**69 engineer-days**, **~83 with 20% contingency**. That is **13–16 weeks for one engineer**, or
**9–10 weeks with two** (one backend/data, one web/reliability). The v1 8-week/57-day schedule was
arithmetically impossible.

## 5. Acceptance metrics

| Area | Gate |
|---|---|
| Types | `py.typed`; `mypy --strict` + `disallow_any_explicit`; `tsc --noEmit` with `allowJs: false`; no `.jsx` under `features/`; CI grep for `as any`/`: any`/`@ts-ignore` = 0 |
| Performance | `bench_api --tasks 10000 --streams 20 --requests 500 --max-p95-ms 250`, seeded by `TaskIndex.replace`, 3 runs, median; fail >250 ms or >120% of `main` two runs in a row |
| Index | 500-task deep-equal index/file summaries; corrupt/old schema rebuild; rebuild budget; no O(N) API path |
| Reliability | 30 crash points, Windows+Linux; terminal job state; owner released; exactly-once fake side effects; no orphan child; readable restart explanation |
| Security | non-loopback pairing/revoke E2E; 20 failed attempts → 429 + Retry-After; audit log assertions; Windows ACL test; pip/npm audit zero high/critical with owner+expiry exceptions |
| Observability | `trace_id` in `Job.as_dict()` and job logs; log-schema test; JSON metrics named counters; SSE slow-consumer test |
| OTel | no-op instrumentation by default; `WORKS_OTEL=1` local exporter; full HTTP→job→subprocess trace; <5% p95 overhead |
| Async | every route classified; hot read paths async/offloaded; worker-starvation test with 20 SSE; job-executor ADR |
| React platform | no `.jsx` under `app/features`; React Compiler decision with size/latency evidence; RSC ADR (expected reject) |
| Accessibility | axe serious/critical = 0 on five screens; screenshots opt-in |
| AI | prompt hash in `run.json` + `evidence.md`; golden set denominators and thresholds; max-regression delta; budget blocked state; hostile-model invariants |
| Release | 3.13 clean-venv wheel install (`--require-hashes`), `doctor`, daemon start/status/stop; SBOM; no signing gate until publish exists |
| Quality | mutation ≥70% on core + new index/job modules; docs link check; `Makefile` `e2e`/`wheel`/`bench` |

## 6. Top risks

1. **Scope inflation toward a platform.** Prometheus, SQLite jobs, signing and installers are
   “modern” but not needed for one home; they crowd out Windows CI, backup and idempotency.
2. **Index/domain drift.** Encoding event-derived risk/decision into SQLite duplicates presenter
   logic or leaks `interfaces/api` into `adapters/`. This version forbids that.
3. **Type migration destabilizes the UI.** 35 `.jsx` files + ESLint + Zod + `allowJs: false` at once
   will break the committed `dist` gate. Slice it screen-by-screen with the current gate green.
4. **False confidence in “secure remote”.** Cleartext bearer, a Windows `chmod` no-op, no audit,
   no session expiry, and rate limiting behind a tunnel are not security. M0 must land code, not
   prose.
5. **“Async-first” and RSC churn.** Rewriting blocking git/subprocess routes or moving a local SPA to
   RSC would add risk without a user-visible requirement. M10 requires measurements and an ADR; RSC
   is expected to be rejected.
6. **Gate-cutting under schedule pressure.** If the plan is compressed, Windows CI, the crash matrix
   and mutation are cut first — exactly the evidence that makes the product trustworthy. Use the
   corrected effort and two engineers where possible.

## 7. Drop or defer (explicit)

- **Drop:** pyright/ty as a second Python checker; native-client Kotlin/C# probe; cursor pagination
  and ETag for a local 200-row page; mobile-web viewport pass; screenshot diffs as a required gate.
- **Defer:** Prometheus, SLO dashboards; provider fallback; SQLite job store and auto-resume;
  Python 3.14 as primary; Sigstore signing, MSI/installer, reproducible build; `just`, MkDocs.
- **Expected reject:** RSC/Next.js for the local SPA; a full async rewrite of blocking routes.
  OTel is **not** deferred: no-op by default, opt-in exporter in M5.7.

## 8. Definition of done

A new engineer can trace one request through types, logs and tests; a 10k queue loads quickly with
20 live streams; a phone pairs and is revoked safely; a crash leaves a deterministic state and a
restorable home; a prompt/model change is measured, not guessed; and a release is reproducible and
verifiable — **without adding a cloud dependency**.
