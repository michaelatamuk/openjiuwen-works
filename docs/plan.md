# Development plan — openJiuwen Works

**Status:** v4.3 · **Owner:** Michael (solo) · **Updated:** 2026-11-21

Every task is a checkbox, checked when its criteria are met and the change is merged. `S/M/L`:
S ≤ half a day, M ≤ two days, L ≤ a week. Nothing is checked because it was started.

Revisions and the reasons behind them: §20. External critiques: `docs/review-1-self.md`,
`docs/review-2-industry.md`, `docs/review-3-external.md`.

---

## 1. Vision

A software factory: one signal goes in, a released fix comes out, and the fix lands back where the
bug was seen. People appear at exactly two gates — the plan and the release.

**v0 promise:** a filed issue becomes a merged change with a one-page proof, and the reporter is
told. "Released" means merged and confirmed; deploy is out of scope.

---

## 2. Problem

Writing code is no longer the bottleneck; waiting is. A fix spends its life in queues: for triage,
for an agent's answers, for a reviewer's time, for someone to prove the change works.

Detail: `docs/deck/`, `docs/video/`.

---

## 3. Non-goals for v0

- No chat surface, no general-purpose coding assistant.
- No deploy, canary or rollback automation. Release = merged PR + confirmation.
- No detector ingestion (DigitalMate) and no person channel beyond the CLI. Both are v1; the README
  says so.
- No web UI before the loop works, no multi-tenant, no SSO, no billing.
- No arbitrary repositories: one fork, one flow, one product.
- No automatic merge to a protected branch.
- No external repositories in v0. The first product is this repository: bugs are filed and fixed here.
  External products, including a real OSS target, are v1.

---

## 4. Invariants

1. **One operator.** A single supervisor advances the task; nothing else moves it.
2. **Two human gates.** Plan and release. Nothing else blocks on a person.
3. **The builder cannot edit the tests it is judged by.** Test paths are denied, the quarantine list
   lives outside the repo, and a test delta is shown on the proof.
4. **The verifier is independent in runtime and provider.** Separate process/container, no builder
   transcript, provider different from the builder's.
5. **Scenarios live outside the repository** and are unreadable from the builder's working directory.
6. **Policy sits outside the agent**, enforced by the runner, not requested from the model.
7. **Events are the truth.** `events.jsonl` is append-only; `task.yaml` is a projection.
8. **Every run records prompt hash, model id and version, cost, duration, verdict.**
9. **Every commit carries its run id.** Trailer `Works-Run: <id>`.
10. **A failure produces a reason**, not an endless retry.

---

## 5. Preconditions — week 0

Cheap checks that can cancel the project.

- [ ] **R1** Run the target repo's full test suite once; record duration, failures, flaky tests,
  required services. **S**
- [ ] **R2** Find a fast path: the subset that catches this class of bug in ≤ 3 minutes. **S**
  - Threshold: fast path ≤ 3 min, full suite ≤ 10 min. Above 5 / 15 min, the plan is revised.
- [ ] **R3** Define the first defect class and write down three candidate defects in our own code:
  the one we will fix first and two fallbacks. **S**
  - Criteria: each is reproducible, touches ≤ 3 files, and a test can prove it.
- [ ] **R3b** Record a proxy for the in-scope rate: of the last 10 defects in this repository (or, while
  there are none, 10 realistic defect descriptions), how many fit the class. **M**
  - The external in-scope rate is measured in v1 on a real product; v0 records the local proxy.
- [ ] **R4** Baseline: how long the same issue class takes a person today, with evidence. **S**
- [ ] **R5** Forge and CI: which API, which token scopes, which commands. **S**
- [ ] **R6** Harness smoke test: one turn, events, cost. **M**
- [ ] **R7** **Manual spike** (the experiment that can cancel everything): run the harness by hand on a
  representative issue in a read-only clone of an unfamiliar codebase — not our repository, because
  the question is capability on code the model has not seen. Record attempts, cost, wall time, and
  whether the result was mergeable. **L**
  - Gate: if it cannot produce a plausible fix in two attempts, stop and re-scope.
- [ ] **R8** Isolation decision (was D6): the verifier runs in a **container** (WSL2/Docker), the
  builder stays on the host with a pinned cwd. Limitations written down. **M**
- [ ] **R9** Write the first three scenarios for the R3 issue, before any code. **M**
- [ ] **R10** Branch policy: short-lived branches from `main`, one PR per task, protected `main`,
  required checks, and no fork. The spike in R7 uses a read-only clone of an external product and
  publishes nothing. **S**

**Gate to proceed:** R1–R9 green, or the plan is revised.

---

## 6. Architecture

```
 signal ─► supervisor ─► reproduce ─► plan ║gate 1║ ─► build ─► check ─► proof ─► release ║gate 2║ ─► return
                │                                                                              │
                └──────────────────────── events.jsonl ──► ledger ◄───────────────────────────┘
```

**Supervisor:** one resumable process (`works run`) that advances state until a gate or a terminal
state. Heartbeat every 10 s; on restart it resumes from the last event. The operator does not click
through nine commands.

### 6.1 Components

| Component | Responsibility |
|---|---|
| `sources` | tracker issue / manual → task, with an idempotency key |
| `queue` | append-only events, task projection, locking |
| `supervisor` | advance, resume, heartbeat, stop with a reason |
| `reproduce` | write a failing test/scenario that fails on the base commit |
| `plan` | spec, scenario ids, approval |
| `runner` | worktree, harness call, command execution, trace |
| `verify` | container, holdout scenarios, verdict |
| `evidence` | computed proof page |
| `metrics` | ledger, escape detection |
| `policy` | paths, gates, budgets — enforced by the runner |

### 6.2 Flows are node graphs (blueprints)

```yaml
flow: fix-issue
nodes:
  - {id: reproduce, kind: agentic}
  - {id: apply,     kind: agentic}
  - {id: lint,      kind: deterministic, cmd: "make check", required: true}
  - {id: tests,     kind: deterministic, cmd: "make test-fast", required: true}
  - {id: ci,        kind: deterministic, cmd: "gh pr checks --watch", required: true}
edges: [[reproduce, apply], [apply, lint], [lint, tests], [tests, ci]]
repair: {attempts: 1, then: ci_retry_1, then: gate_release}
```

Deterministic nodes never call a model and cannot be skipped by the agent.

### 6.3 Data

- **Events** — `queue/<id>/events.jsonl`, append-only, the only writer is the supervisor.
- **Task projection** — derived; never edited by hand.
- **Run** — `runs/<id>/run.json`: prompt hash, model id + version, provider, attempts, cost, duration.
- **Verdict** — `runs/<id>/verdict.json`: per-scenario, weights, blocking failures.
- **Evidence** — `runs/<id>/evidence.md` (rendered) + `evidence.json` (computed).
- **Ledger** — `ledger.jsonl`; plus `ledger/escapes.jsonl` for post-release attribution.
- **Idempotency** — `(source.kind, source.ref)`; a duplicate webhook returns the existing task.

### 6.4 Engineering standard — 2026, not optional

Every commit satisfies this. It is checked in CI, not in review comments.

**Language and shape**

- Python **3.12**, `from __future__ import annotations`, type hints on every public function.
- `mypy --strict` on `src/`; no `Any` without a one-line reason; no `# type: ignore` without a code.
- `ruff` for lint and format; no warnings, no unused imports, no dead code.
- Async for I/O; `asyncio.TaskGroup` for structured concurrency; no bare threads.
- Pure functions where possible; side effects at the edges; dependencies injected, not imported globally.
- One module, one reason to change. Domain types never import infrastructure.
- Errors: a typed exception hierarchy per component; `except Exception` only to log, add context and
  re-raise or convert into a stop reason.
- Structured JSON logs with `run_id`, `task_id`, `step`; no `print`.
- Config via pydantic settings; secret names documented; secrets never in files or prompts.
- Every persisted record carries `schema_version`; a migration function per bump.

**Tooling**

`uv` (env, lock) · `ruff` · `mypy` · `pytest` · `hypothesis` · `mutmut` · `bandit` · `pip-audit` ·
`gitleaks` · `pre-commit` · `cyclonedx` SBOM on release.

**Testing**

- Property-based tests for the state machine and path policy (adversarial paths, `..`, unicode).
- Contract tests for the harness adapter against recorded traces.
- Golden-file tests for evidence rendering; a change to the page is a reviewed diff.
- Mutation score ≥ 70% on `queue/`, `policy/`, `verify/`.
- Load test: 10 000 tasks in the queue, `status` still under 100 ms.

**Budgets**

- CLI cold start < 300 ms; `status` command logic < 100 ms (process startup excluded);
  evidence render < 1 s. Measured on the development host by `scripts/bench.py`: 206 ms, 59 ms at
  10 000 tasks, 0.02 ms.
- No dependency without a reason; a new dependency requires an ADR line.

**Every PR**

`make check` green (ruff, mypy, pytest), no new TODOs, docs updated, and if the change touches a
decision, an ADR is added or amended.

**Reliability**

- Every external call has a timeout, a bounded retry with jitter, and a typed failure.
- Circuit breaker around the model provider: after N consecutive failures, stop and say so; never
  loop on a dead provider.
- Idempotent everywhere it matters: submit, publish, comment, revert.
- Graceful degradation: if the verifier cannot run, the task blocks — it never "passes by default".

**Reproducibility**

- `uv.lock` committed; exact versions pinned; model id and version recorded per run.
- Fixed seeds in tests; recorded traces replayed in CI, not live model calls.
- `works schema` prints every persisted schema; a migration is tested with old fixtures.

**Supply chain**

- Pinned dependency hashes; `pip-audit` and Dependabot/Renovate weekly; `cyclonedx` SBOM per release.
- `gitleaks` on every push; signed commits from v0.2 onward.
- No dependency added without a reason in the PR and a line in the ADR.

**AI-specific quality**

- Prompts are versioned files with a hash; a prompt change requires a benchmark run before adoption.
- Every agent output that drives a decision is JSON validated by a schema — never parsed free text.
- The verifier runs at temperature 0 where the provider allows it, and the setting is recorded.
- Cost per step is captured from harness events and attributed to the run budget.
- Injection guard: issue text is fenced as data; the policy engine, not the model, enforces paths.
- A prompt change and a model change are never shipped in the same commit.

**Observability**

- Structured events carry `run_id`, `task_id`, `step`, `duration_ms`, `tokens`, `usd`.
- `works trace <run>` renders the timeline from events; nothing is reconstructed from logs.
- OpenTelemetry spans are optional in v0 but the event schema is ready for them.

**Process**

- Trunk-based, small PRs (< 400 changed lines), conventional commits, PR template asks for evidence.
- `CHANGELOG.md` per release; `docs/runbook.md` for known failures and their first response.
- Renovate weekly; a dependency update that breaks a test is fixed or reverted the same day.

### 6.5 GUI standard — if a GUI is built

v0 is CLI-first. If and when a window is built, it is a separate `web/` app and it meets this bar.

**Stack**

React 19 + TypeScript strict + Vite + Tailwind CSS v4 + shadcn/ui (Radix primitives) +
TanStack Query; SSE for live runs; Playwright + axe for tests; visual snapshots for regressions.

**Design**

- Design tokens for colour, space, radius and type; light and dark from one source.
- Inter or Geist; 4/8 pt spacing scale; one accent colour (purple); no decorative gradients.
- Depth from a single shadow scale; borders over shadows for structure.
- Density toggle: comfortable and compact, same information, no reflow surprises.

**Interaction**

- Keyboard-first: `⌘K` command palette, `g` sequences, visible focus, escape everywhere.
- Streaming run progress over SSE; skeletons instead of spinners; optimistic updates with rollback.
- Inline diff with syntax highlighting; every run, step and artifact has a deep link.
- Empty, loading, error and blocked states designed, not defaulted.

**Accessibility and performance**

- WCAG 2.2 AA: contrast ≥ 4.5:1, focus visible, `prefers-reduced-motion` respected, labels on every
  control, status never conveyed by colour alone.
- LCP < 1.5 s locally, INP < 200 ms, no layout shift, initial bundle < 250 kB gzip.
- Tables virtualised beyond 100 rows; no modal for a primary flow.

**Testing**

Playwright end-to-end on the three primary flows, axe checks in CI, screenshot diffs on every PR
that touches `web/`.

### 6.6 Refactoring gates

Refactoring is scheduled, not improvised. Each gate is a task with a definition of done; no new
feature work starts until it closes.

- [ ] **RG0** after M0.5 — remove fake-harness seams that leaked into real code; align interfaces
  with the real protocol; delete scaffolding. **S**
  - Status 2026-11-21: scaffolding is isolated in `harness/fake.py` and the CLI `--trace` flag. The
    real adapter cannot be aligned until the R7 spike and provider credentials exist. Gate stays
    open on purpose.
- [ ] **RG1** after M1 — extract the supervisor from CLI commands; unify command execution; strict
  typing everywhere; remove dead paths. **M**
- [ ] **RG2** after M2 — split `verify` and `evidence`; introduce ports for forge, CI and scenarios;
  no concept leaks between them. **M**
- [ ] **RG3** after M3 — consolidate adapters; audit idempotency; finalise the error taxonomy; remove
  duplicated retry logic. **M**
- [ ] **RG4** after M4 — cost and performance pass; consolidate prompts and flows; documentation
  sweep; benchmark before and after. **M**

Definition of done for a gate: tests green, mutation ≥ 70% on core, no new TODOs, complexity within
limits, benchmark not regressed, ADR if the structure changed.

**Continuous triggers** — act at the next gate, or immediately if a test breaks:

file > 400 lines · function > 50 lines · cyclomatic complexity > 10 · a duplicated block in three
places · module fan-in > 7 · an unexplained `# type: ignore` · a TODO older than 14 days · an unused
dependency · a test slower than 2 s.

---

## 7. One run

1. `works submit --issue …` → task, dedupe.
2. Supervisor: **reproduce** — a failing test on the base commit; it must fail, and the failure is
   stored. If it cannot be made to fail, the run stops with `not_reproducible`.
3. Plan: spec names the scenario ids it will be judged by. **Gate 1.**
4. Build in a worktree; deterministic nodes run unconditionally.
5. Check: verifier container, holdout scenarios, verdict (`all P0 pass` or block).
6. Proof: computed page. **Gate 2**, bound to the commit.
7. Publish: branch, PR with the proof, `Works-Run:` trailer, one comment on the issue.
8. Confirm: re-run the reproduction; arm the escape window.
9. Revert path if confirmation fails.

---

## 8. Milestones

### M0 — Skeleton (week 1)

- [x] **T0.1** Package, editable install, `works --help`. **S**
- [x] **T0.2** Event model + task projection + locking. **M**
  - Criteria: replaying events rebuilds the same task; two supervisors cannot both own a task.
  - Done: `queue.py`, `state.py`; property test over transitions; claim uses `O_EXCL`.
- [x] **T0.3** `works submit` with idempotency. **S**
  - Criteria: the same issue twice yields one task.
- [x] **T0.4** Flow schema with node kinds and required nodes. **S**
- [x] **T0.5** Policy: allow/deny with normalized segments, deny-wins, `..` rejected, **test paths
  denied by default** (`**/test_*.py`, `conftest.py`, `pytest.ini`, quarantine file). **M**
  - Criteria: an adversarial path table passes; a test edit is refused before any command runs.
- [x] **T0.6** Ledger writer with schema version. **S**
- [x] **T0.7** `works status`, `works run --dry-run`. **S**
- [x] **T0.8** Toolchain in CI and pre-commit: ruff, mypy strict, pytest, hypothesis, mutmut baseline,
  bandit, pip-audit, gitleaks, coverage gates. **M**
  - Criteria: a PR with a type error, a leaked secret, untested code or a low mutation score fails.
  - Done: `Makefile`, `scripts/check.ps1`, `.pre-commit-config.yaml`, CI + weekly mutation and
    supply-chain workflows. Mutmut has no native Windows support, so the mutation gate is verified
    on the Linux CI job; measured 71.8% (519/723) on state, policy and queue. Local runs cover ruff,
    mypy, pytest and coverage.
- [x] **T0.8b** `works schema` prints JSON Schemas for task, run, verdict, event; a fixture from the
  previous schema version loads through a migration. **S**
- [x] **T0.8c** `--json` output and stable exit codes for every command; no interactive prompt when
  `CI=1`. **S**
- [x] **T0.9** `works doctor`: config, git, harness, container, scenario dir, credentials. **M**
- [x] **T0.10** Quarantine list lives outside the repo; the runner refuses to read one inside. **S**

**Demo M0:** submit → dry run → a test edit refused → ledger row.

_Delivered 2026-11-21: `works` CLI, event store, policy, ledger, doctor, schema, quarantine;
demo in `docs/demo-m0.md`._

### M0.5 — Walking skeleton (week 2)

- [x] **T0.11** Fixture repo: planted bug, failing test, three scenarios. **S**
- [x] **T0.12** Fake harness replaying a trace. **M**
- [x] **T0.13** Supervisor end to end: reproduce → apply → tests → evidence. **M**
- [x] **T0.14** Integration test in CI: whole loop, no model call. **M**
- [x] **T0.15** Failure paths: `not_reproducible`, `blocked`, `reverted`. **S**
  - Done: `not_reproducible`, policy, tests, verdict, harness abstention, budget and dirty-tree
    paths are integration tests. `reverted` and the escape flag are exercised through the state
    machine and the ledger; the publish/confirm path lands in M3.

**Demo M0.5:** `pytest tests/integration` runs the full loop with no model.

_Delivered 2026-11-21: 15 integration tests (happy path, preapproved plan, plan gate resume,
not reproducible, policy, sneaky patch, abstention, token and wall budgets, quarantine, dirty tree,
revert/escape). `make integration`._

### M1 — One loop, scenarios first (weeks 3–5)

Internal only: nothing is published to the upstream fork until M2 is green.

- [ ] **T1.1** Scenario loader/validator with weights and P0/P1. **M**
- [ ] **T1.2** Scenario set for the R3 issue: at least three P0, written before build. **M**
  - Criteria: every P0 fails on the base commit.
- [ ] **T1.3** Repo adapter: clone/reuse, base commit pinned, dirty tree refused. **M**
- [ ] **T1.4** Worktree manager, symlink and `..` escape refused. **M**
- [ ] **T1.5** Harness adapter: events → trace, model id recorded, cost per attempt. **L**
- [ ] **T1.6** Reproduce step: agent writes a failing test; the runner verifies it fails on base. **L**
- [ ] **T1.7** Plan drafting, scenario ids in the spec, gate 1. **M**
- [ ] **T1.8** Build with bounded repair: 1 repair + 1 CI retry, then `needs_person`. **M**
- [ ] **T1.9** Command runner: timeout, process-tree kill, path escape check, network policy. **M**
- [ ] **T1.10** Evidence v1 computed: diff stat, test deltas, commands, exit codes, cost. **M**
- [ ] **T1.11** Test-delta and suspicious-change list on the proof; gate refuses auto-allow while
  non-empty. **M**
- [ ] **T1.12** Supervisor resume: kill mid-run, restart, continue from the last event. **M**
- [ ] **T1.13** Two of three candidate issues complete end to end. **L**

**Demo M1:** two real issues go from ticket to proof, twice in a row, with scenarios written first.

### M2 — Proving the verifier (week 6)

- [ ] **T2.1** Verifier container: worktree mounted read-only, scenarios mounted only there. **L**
- [ ] **T2.2** Leak tests: builder cannot read scenarios; every builder-readable artifact is grepped
  for scenario strings. **M**
- [ ] **T2.3** Provider split: verifier provider ≠ builder provider, recorded in `run.json`. **S**
- [ ] **T2.4** Mutation check in CI: reverting the diff turns a P0 red. **M**
- [ ] **T2.5** **Sneaky patches**: for each P0, a patch that satisfies the literal issue but breaks
  adjacent behaviour; the scenario must go red. **L**
- [ ] **T2.6** Abstain test: a similar-looking non-bug must not be "fixed". **M**
- [ ] **T2.7** Judge calibration: 10 scenarios scored by a human and by the judge; delta recorded;
  block if disagreement > 2. **M**
- [ ] **T2.8** Verdict rule: all P0 pass, P1 ≥ 80%, else block. **S**
- [ ] **T2.9** Evidence v2: verdict, failures, cost, **what was not tested**. **M**

**Demo M2:** a patch that passes CI and the builder's tests is caught by a sneaky-patch scenario.

### M3 — Release, return, escape (weeks 7–8)

- [ ] **T3.1** Release gate: normalized path matching, deny-wins, approval bound to commit hash. **M**
- [ ] **T3.2** Publish asserts `HEAD == approved_commit`; otherwise re-gate. **S**
- [ ] **T3.3** Branch + PR with proof, `Works-Run:` trailer, bot identity. **M**
- [ ] **T3.4** Return: one comment per run on the source issue, idempotent. **M**
- [ ] **T3.5** Confirm: re-run the reproduction; result recorded. **M**
- [ ] **T3.6** **Escape detection**: arm a 14-day window per release; a revert, hotfix or red main
  touching the same paths attributes a row to the release. **L**
- [ ] **T3.7** Revert path: revert PR, note, post-mortem, ledger row. **M**
- [ ] **T3.8** Human minutes from gate timestamps. **S**

**Demo M3:** issue → merged PR → proof → comment → green reproduction; then a forced revert attributed
to its release.

### M4 — Second flow, learning, benchmarks (weeks 9–10)

- [ ] **T4.1** `docs.yaml`: documentation flow, automatic release only after T3.6 is green. **M**
- [ ] **T4.2** Routing from the signal, not a flag. **M**
- [ ] **T4.3** Scorers: rubric on a 25% sample, separate from the verdict. **M**
- [ ] **T4.4** Benchmark suite: five past tasks replayed at their initial state. **L**
- [ ] **T4.5** Prompt/model comparison using the benchmark before any change is adopted. **M**
- [ ] **T4.6** Learning loop: repeated failure → proposed rule/test/scenario as a PR; never automatic. **L**
- [ ] **T4.7** In-scope rate measured on new issues; report next to the metrics. **S**

**Demo M4:** two flows, one benchmark that chose a cheaper configuration, one failure that became a
scenario through a reviewed PR.

---

## 9. Gates and policy

```yaml
paths:
  deny: ["migrations/", ".github/workflows/", "**/test_*.py", "conftest.py", "pytest.ini"]
  allow: ["backend/", "frontend/src/"]
gates:
  - {on: plan, action: ask}
  - {on: release, when_paths: ["backend/", "auth/"], action: ask}
  - {on: release, when_paths: ["docs/"], action: allow, unless: suspicious}
budget: {tokens: 400000, usd: 10, wall_minutes: 60, ci_minutes: 30}
```

Rules: segments normalized before matching; deny wins; `..` rejected; auto-allow refused while the
suspicious list is non-empty; approval is bound to the commit and re-checked at publish.

---

## 10. Scenarios

- Written **before** the build, by the owner of the intent, reviewed like code, stored outside the repo.
- One scenario per risk. Each declares weight (P0/P1), setup, command, expected observation.
- Every P0 must fail on the base commit.
- Deterministic checks first; an LLM judge only for qualitative observations.
- Every scenario states what it does **not** cover.
- **What the verifier sees:** the worktree read-only, the scenario, and the issue's *reproduced*
  behaviour. Never the builder transcript, never the raw issue text.

---

## 11. Evidence (computed, not narrated)

The page shows, from data: diff stat, files changed, test add/remove/modify counts, assertion delta,
skipped-test delta, dependency and lockfile delta, commands and exit codes, verdict, cost, duration,
and a mechanical suspicious-change list (deleted tests, new skips, broad except, disabled features).

---

## 12. Security

- [ ] **SEC1** Prompt scan for secrets before send. **S**
- [ ] **SEC2** Builder: pinned cwd, path-escape refusal, network allowlist, no production credentials. **M**
- [ ] **SEC3** Only `works publish` can push; the git remote is behind the runner. **M**
- [ ] **SEC4** Issue text is data, never instructions; explicit guard in the prompt. **S**
- [ ] **SEC5** Retention policy: traces kept N days, customer text redacted. **M**
- [ ] **SEC6** Known limitation documented: v0 builder shares the host user; v1 moves it into a container. **S**

---

## 13. Metrics

| Metric | Definition | Target |
|---|---|---|
| Time to fix | signal → merged + confirmed | < 1 working day |
| Proof coverage | releases with a computed proof | 100% |
| Human minutes | sum of gate durations | < 15 |
| Escapes | attributed within 14 days per 100 releases | < 5 |
| Cost | USD per release, verifier included | < $15 |
| In-scope rate | share of new issues the flow can take | reported, not targeted |

---

## 14. Testing

- Unit: state machine, policy table (adversarial paths), scenario loader, evidence computation.
- Property-based: state machine and path policy with hypothesis (unicode paths, `..`, symlinks).
- Contract: harness adapter against recorded traces; no live model in CI.
- Golden files: evidence rendering, so a page change is a reviewed diff.
- Integration: fixture repo + fake harness, the whole loop in CI.
- Mutation and sneaky-patch suites in CI; mutation ≥ 70% on core.
- Leak test: grep every builder-readable artifact for scenario strings.
- Load: 10 000 tasks in the queue; `status` under 100 ms.
- Performance: CLI start, evidence render and report timed in CI; fail on > 20% regression.
- One manual end-to-end per milestone, recorded.

---

## 15. Risks

| Risk | Mitigation |
|---|---|
| Builder edits tests | Deny by default; test delta on proof; quarantine outside repo |
| Holdout leaks | Separate container, read-only mount, artifact grep |
| Verifier too weak | Mutation + sneaky patches + abstain test |
| Verifier too strict | Weights and P0/P1; calibration |
| Token blow-up | Hard abort at 80%, per-attempt cost, output compaction |
| Harness API move | Pinned commit, adapter |
| Target repo drift (v1) | Sync before run; divergence in evidence |
| Dogfooding hides real-world mess | R7 runs on an unfamiliar codebase, not ours |
| Solo bottleneck | R7 spike first; S/M/L sizing |

---

## 16. Kill criteria

Stop if any holds after M1:

- Fast path > 5 minutes, or full suite > 15 minutes.
- The harness cannot produce a mergeable fix in two attempts on two of three issues.
- The proof cannot be produced without a human reading the diff.
- Cost > 2× target for three consecutive runs.
- Judge disagrees with a human on > 2 of 10 scenarios.

---

## 17. Open decisions

All decided; revisit only with an ADR.

- [x] **D1** Target: **this repository**. The factory fixes defects in its own code (dogfooding);
  branches in place, no fork. An external OSS product is v1.
- [x] **D2** Engine location: developer machine; the verifier runs in a container on the same host.
- [x] **D3** Models: builder on one frontier coding model, verifier on a different provider; ids pinned
  in config and recorded per run.
- [x] **D4** License: Apache-2.0.
- [x] **D5** Release gate: Michael owns it; from M3 a second reviewer is required for `auth/`.
- [x] **D6** Isolation: verifier in a container; builder on host with pinned cwd (v0).
- [x] **D7** Forge: GitHub first; a GitCode adapter interface exists but is unimplemented in v0.

---

## 18. Definition of done

A milestone is done when the demo runs twice, the ledger has rows, the proof is readable without
narration, the limitations are written down, **the engineering standard in §6.4 holds for every
touched file**, and **the refactoring gate that follows it (§6.6) is closed**.

---

## 19. Not in this plan, on purpose

Detector ingestion, person channel beyond CLI, deploy/canary, web UI, multi-repo, multi-tenant.
Each has a sentence in §3 and no task.

---

## 20. Changelog

- **v4.3** — M0 and M0.5 delivered: queue, replay, idempotent submit, claims, derived SQLite index,
  path policy, flow schema, ledger, evidence, fake harness, fixture repo, supervisor and all failure
  paths; CLI rewritten on argparse to meet the start budget; budgets measured and recorded.
  Mutation gate runs in Linux CI because mutmut has no native Windows support. RG0 remains open:
  the openjiuwen adapter needs the R7 spike and provider credentials.
- **v4.2** — target changed to this repository (dogfooding, branches in place, no fork); `open-webui`
  is used only as a read-only clone for the R7 capability spike; in-scope rate recorded as a local
  proxy in v0 and measured externally in v1.
- **v4.1** — target remote decided: a public fork with an `upstream` remote, a sync step before runs,
  divergence recorded; v0 publishes PRs inside the fork only (R10, non-goal updated).
- **v4** — added the engineering standard (§6.4) with reliability, reproducibility, supply chain,
  AI-specific quality, observability and process rules; the GUI standard (§6.5); scheduled
  refactoring gates RG0–RG4 with continuous triggers (§6.6); toolchain, schema and CLI-contract
  tasks; expanded testing and definition of done; all open decisions taken (D1–D7).
- **v3** — from external review and industry practice: scenarios moved before the build; test paths
  denied and quarantine moved outside the repo; verifier isolation decided (container) and leak tests
  added; provider split; sneaky-patch and abstain suites; judge calibration; computed evidence; commit
  binding at publish; escape detection in M3; supervisor loop, events as truth, idempotency; budget
  abort at 80%, wall-clock and CI budgets; in-scope rate over 40 issues; harness spike in week 0;
  reproduce step; blueprint node model; bounded repair (1+1); prepared environment; model id in trace;
  `Works-Run:` trailer; fork drift, blocked-task inbox, retention.
- **v2** — reconnaissance, walking skeleton, scenario method, leak guard, revert, learning loop.
- **v1** — first draft.
