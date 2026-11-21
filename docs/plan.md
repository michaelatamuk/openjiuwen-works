# Development plan — openJiuwen Works

**Status:** v3 · **Owner:** Michael (solo) · **Updated:** 2026-11-21

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
- [ ] **R3** Pick the v0 issue: user-filed, reproducible, ≤ 3 files, no migrations, provable by a
  test. **S**
- [ ] **R3b** Label the last 40 issues in the fork as in-scope / out-of-scope and record the rate. **M**
  - Gate: below 15% in-scope, the product thesis is wrong for this repo.
- [ ] **R4** Baseline: how long the same issue class takes a person today, with evidence. **S**
- [ ] **R5** Forge and CI: which API, which token scopes, which commands. **S**
- [ ] **R6** Harness smoke test: one turn, events, cost. **M**
- [ ] **R7** **Manual spike** (the experiment that can cancel everything): run the harness by hand on
  the R3 issue. Record attempts, cost, wall time, and whether the result was mergeable. **L**
  - Gate: if it cannot produce a plausible fix in two attempts, stop and re-scope.
- [ ] **R8** Isolation decision (was D6): the verifier runs in a **container** (WSL2/Docker), the
  builder stays on the host with a pinned cwd. Limitations written down. **M**
- [ ] **R9** Write the first three scenarios for the R3 issue, before any code. **M**

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

- [ ] **T0.1** Package, editable install, `works --help`. **S**
- [ ] **T0.2** Event model + task projection + locking. **M**
  - Criteria: replaying events rebuilds the same task; two supervisors cannot both own a task.
- [ ] **T0.3** `works submit` with idempotency. **S**
  - Criteria: the same issue twice yields one task.
- [ ] **T0.4** Flow schema with node kinds and required nodes. **S**
- [ ] **T0.5** Policy: allow/deny with normalized segments, deny-wins, `..` rejected, **test paths
  denied by default** (`**/test_*.py`, `conftest.py`, `pytest.ini`, quarantine file). **M**
  - Criteria: an adversarial path table passes; a test edit is refused before any command runs.
- [ ] **T0.6** Ledger writer with schema version. **S**
- [ ] **T0.7** `works status`, `works run --dry-run`. **S**
- [ ] **T0.8** CI: pytest, ruff, mypy. **S**
- [ ] **T0.9** `works doctor`: config, git, harness, container, scenario dir, credentials. **M**
- [ ] **T0.10** Quarantine list lives outside the repo; the runner refuses to read one inside. **S**

**Demo M0:** submit → dry run → a test edit refused → ledger row.

### M0.5 — Walking skeleton (week 2)

- [ ] **T0.11** Fixture repo: planted bug, failing test, three scenarios. **S**
- [ ] **T0.12** Fake harness replaying a trace. **M**
- [ ] **T0.13** Supervisor end to end: reproduce → apply → tests → evidence. **M**
- [ ] **T0.14** Integration test in CI: whole loop, no model call. **M**
- [ ] **T0.15** Failure paths: `not_reproducible`, `blocked`, `reverted`. **S**

**Demo M0.5:** `pytest tests/integration` runs the full loop with no model.

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
- Integration: fixture repo + fake harness in CI.
- Mutation and sneaky-patch suites in CI.
- Leak test: grep every builder-readable artifact for scenario strings.
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
| Fork drift | Rebase job and upstream divergence in evidence |
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

- [ ] **D1** Target: `open-webui` fork (default).
- [ ] **D2** Engine location: developer machine first.
- [ ] **D3** Model routing: builder and verifier on different providers (required), specific models TBD.
- [ ] **D4** License.
- [ ] **D5** Release gate owner.
- [x] **D6** Isolation: verifier in a container; builder on host with pinned cwd (v0).
- [ ] **D7** Forge adapter: GitHub first.

---

## 18. Definition of done

A milestone is done when the demo runs twice, the ledger has rows, the proof is readable without
narration, and the limitations are written down.

---

## 19. Not in this plan, on purpose

Detector ingestion, person channel beyond CLI, deploy/canary, web UI, multi-repo, multi-tenant.
Each has a sentence in §3 and no task.

---

## 20. Changelog

- **v3** — from external review and industry practice: scenarios moved before the build; test paths
  denied and quarantine moved outside the repo; verifier isolation decided (container) and leak tests
  added; provider split; sneaky-patch and abstain suites; judge calibration; computed evidence; commit
  binding at publish; escape detection in M3; supervisor loop, events as truth, idempotency; budget
  abort at 80%, wall-clock and CI budgets; in-scope rate over 40 issues; harness spike in week 0;
  reproduce step; blueprint node model; bounded repair (1+1); prepared environment; model id in trace;
  `Works-Run:` trailer; fork drift, blocked-task inbox, retention.
- **v2** — reconnaissance, walking skeleton, scenario method, leak guard, revert, learning loop.
- **v1** — first draft.
