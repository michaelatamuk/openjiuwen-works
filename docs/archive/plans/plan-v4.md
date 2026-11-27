# Development plan — openJiuwen Works (v4.24, archived)

> **Doc status:** archived · **Owner:** Michael · **Last reviewed:** 2026-11-21

> Archived: this is the original v4.24 plan, kept for history. The stable design is
> [architecture.md](../../design/architecture.md), the current status is
> [status.md](../../start/status.md), and the engineering bar is
> [engineering-standard.md](../../design/engineering-standard.md).

**Version:** v4.24 · **Owner:** Michael (solo) · **Updated:** 2026-11-21

Every task is a checkbox, checked when its criteria are met and the change is merged. `S/M/L`:
S ≤ half a day, M ≤ two days, L ≤ a week. Nothing is checked because it was started.

Revisions and the reasons behind them: §20. External critiques: `docs/archive/reviews/review-1-self.md`,
`docs/archive/reviews/review-2-industry.md`, `docs/archive/reviews/review-3-external.md`, `docs/archive/reviews/review-4-factories.md`,
`docs/archive/reviews/review-5-slop.md`.

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

Detail: `docs/presentation/assets/deck/`, `docs/assets/film/two-mondays.mp4`.

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
11. **Checks outlive changes.** Policy, flows, scenarios, review rules and risk rules are read from the
    trusted base, never from the worktree. A change cannot edit the check that judges it; changing a
    check is a separate task with its own proof.
12. **A verdict is bound to the exact commit.** A new commit invalidates the verifier result,
    challenger verdict and approval; the gate re-checks at the commit being merged.
13. **Every new gate starts in observe mode.** It logs what it would block until its false positives
    are reviewed; only then can it enforce.
14. **No blocking prompt in the engine path.** A question to a person becomes a wait with a wake
    event, a deadline and a default.
15. **External actions are idempotent and safe to repeat.** A retry never duplicates a merge, a
    comment, a release or a task.

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
| `decision` | optional LAIX adapter: `act / ask / wait / verify / escalate` at the gates and for attention routing; the deterministic gate remains the fallback |

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
- Findings that drive a decision are structured records with evidence refs; free-form prose is
  never parsed into one.
- No agent grades its own work: challengers and verifiers are separate sessions and, where
  possible, separate providers.
- Every prompt is a versioned file with a hash; the hash is recorded in the run and the proof.

**Observability**

- Structured events carry `run_id`, `task_id`, `step`, `duration_ms`, `tokens`, `usd`.
- `works trace <run>` renders the timeline from events; nothing is reconstructed from logs.
- OpenTelemetry spans are optional in v0 but the event schema is ready for them.

**Process**

- Trunk-based, small PRs (< 400 changed lines), conventional commits, PR template asks for evidence.
- `CHANGELOG.md` per release; `docs/guides/operations/runbook.md` for known failures and their first response.
- Renovate weekly; a dependency update that breaks a test is fixed or reverted the same day.

### 6.5 GUI standard — if a GUI is built

v0 is CLI-first. If and when a window is built, it is a separate `web/` app and it meets this bar.

**Stack**

React 19 + TypeScript strict + Vite + TanStack Query; the existing CSS is kept for now; a
Tailwind/shadcn decision is deferred (the stack migration chose no Tailwind). SSE for live runs;
Playwright + axe and opt-in visual snapshots are the 2026 target.

**Design**

- Design tokens for colour, space, radius and type; light and dark from one source.
- Inter or Geist; 4/8 pt spacing scale; one accent colour (purple); no decorative gradients.
- Depth from a single shadow scale; borders over shadows for structure.
- Density toggle: comfortable and compact, same information, no reflow surprises.

**Interaction**

- Keyboard-first: `⌘K` command palette, `g` sequences, visible focus, escape everywhere.
- Streaming run progress over SSE; skeletons instead of spinners; optimistic updates with rollback.
- Inline diff with syntax highlighting; every run, step and artifact has a deep link.
- Empty, loading, error and blocked states designed, not defaulted. Mira (the magpie courier)
  appears in empty, waiting, proved and blocked states, never as a chat avatar, never instead of
  status text, and never inside an error message as a joke; motion stops under
  `prefers-reduced-motion`.

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

- [x] **RG0** after M0.5 — remove fake-harness seams that leaked into real code; align interfaces
  with the real protocol; delete scaffolding. **S**
  - Closed 2026-11-21: `LiveHarness` drives `openjiuwen`'s `ClaudeCodeHarness`; the fake harness is
    an explicit test double behind `--trace`; `Proposal.applied` carries worktree edits; bytecode
    artifacts are filtered before policy. CI still uses recorded traces by design.
- [ ] **RG1** after M1 — extract the supervisor from CLI commands; unify command execution; put the
  decision port, trusted-base checks and risk rating behind the supervisor; strict typing everywhere;
  remove dead paths. **M**
- [ ] **RG2** after M2 — split `verify` and `evidence`; introduce ports for forge, CI, scenarios,
  decisions, readiness and preview; no concept leaks between them; add the adversarial challenge,
  the agent eval suite, review-the-reviewers, readiness and the feature map. **M**
- [ ] **RG3** after M3 — consolidate adapters; audit idempotency; finalise the error taxonomy; remove
  duplicated retry logic; move waiting states, wake events, decision outcomes, rollback and the stop
  switch into one dispatcher. **M**
- [ ] **RG4** after M4 — cost and performance pass; consolidate prompts, flows, checks and docs;
  documentation sweep; benchmark before and after; audit attention metrics, decision calibration,
  comprehension sample, friction map, verification cost share and slop signals from events only. **M**

Definition of done for a gate: tests green, mutation ≥ 70% on core, no new TODOs, complexity within
limits, benchmark not regressed, ADR if the structure changed.

**Continuous triggers** — act at the next gate, or immediately if a test breaks:

file > 400 lines · function > 50 lines · cyclomatic complexity > 10 · a duplicated block in three
places · module fan-in > 7 · an unexplained `# type: ignore` · a TODO older than 14 days · an unused
dependency · a test slower than 2 s.

### 6.7 Decision layer — LAIX

**What it is.** [LAIX](https://github.com/michaelatamuk/laix) is our own decision layer: a
dependency-free Python package (`laix==0.18.0`, Apache-2.0) that answers one question — given what is
happening, what the app can afford and what needs approval, should it `wait`, `observe`, `guide`,
`ask`, `act`, `verify` or `escalate`? It returns a `Decision` with a reason code, confidence, score,
approval flag, alternatives and a trace id. It is not an agent framework, a workflow engine, a model
or a verifier.

**Why it is here.** Today a gate is a hard-coded rule (`action: ask`). That is correct but opaque: it
cannot say *why*, how confident it is, what it would have done instead, or how much human attention
the choice costs. LAIX makes the gate an explicit, recorded decision and gives us one ranking
mechanism for the attention inbox. The factory already needs both (D10, D11).

**The boundary — read this before touching the adapter.**

| LAIX does | Works does |
|---|---|
| Chooses a verb and a reason for a gate | Enforces path policy, budgets and the state machine |
| Ranks pending decisions by attention cost | Owns the queue, timers, waits and wake events |
| Carries approvals and commitments into the next decision | Binds approval to a commit and re-checks it at publish |
| Emits a decision record | Owns `events.jsonl`, the ledger and the proof |

LAIX can never open a gate, allow a denied path, replace the verifier, skip a deterministic node or
write state. **Path deny wins before LAIX is consulted; the verifier's verdict wins after it.** A
missing, invalid or low-confidence decision falls back to the deterministic gate — it never fails
open. LAIX never calls the builder or the verifier; it only reads their recorded results.

**Interface.** One port, two adapters:

```python
class DecisionPort(Protocol):
    def decide(self, request: GateContext) -> GateVerdict: ...

class DeterministicGate:   # default, no dependency
    ...

class LaixGate:            # extra: works[decision]
    ...
```

`GateContext` is built only from recorded evidence: reproduced failure, plan spec and scenario ids,
verifier verdict, policy result, diff size, touched paths, budget left, deadline and open
commitments. `Decision.to_dict()` is stored whole as a `decision.made` event and as the **Decision**
section of the proof (`decision_id`, `trace_id`, `verb`, `reason_code`, `confidence`,
`requires_approval`, `alternatives`, `constraints_applied`). Code branches on `reason_code`, never on
`rationale`.

| LAIX verb | Works transition |
|---|---|
| `act`, no approval | plan approved / release proceeds |
| `act`, approval or `ask` / `guide` | `waiting_review` with a wake event and deadline |
| `wait` | `waiting_ci` / `waiting_deploy` / `waiting_review` with a deadline and default |
| `verify` | run the verifier or missing scenarios first, then decide again |
| `observe` | request more evidence; do not advance |
| `escalate` | `blocked`, needs a person |

**Rollout.** `WORKS_DECISION=off | shadow | laix`, default `off` and a per-gate override.

1. **Shadow** — LAIX computes the decision; Works executes the deterministic one; every difference is
   recorded and counted. No transition changes.
2. **Opt-in** — only the plan and release gates may consume LAIX, after the shadow comparison in
   T2.14 shows no case where LAIX allows what policy or the verifier refuses.
3. **Attention** — `AttentionScheduler` ranks waiting tasks and gate requests under an explicit
   `human_attention_budget`; `works attention` and the GUI show selected and deferred decisions.
4. **Commitments** — M3: `CommitmentGraph` carries `approved commit`, `CI green` and `return to the
   issue`; a hard violation becomes `verify` or `ask`. Promises are not a security boundary.

**Known limits of 0.18.0.** Pre-1.0 (schema 0.8.0) with external validation pending, so the adapter
is pinned and conformance-tested rather than imported across the codebase. The default action policy
returns `reason_code=policy_rule` for every path and does not propagate `Decision.reversible` from the
chosen option; it also defaults to `wait` unless urgency/uncertainty are supplied. Works therefore
derives urgency, risk and uncertainty from evidence — never from agent prose (D11) — and uses its own
`DecisionPolicy` when richer reason codes are needed. The LAIX app kit (execution, proposal store,
delivery) is out of scope: Works is the host and already owns those.

### 6.8 Verification and approval boundaries

The gate is the product. A change may be fast to write and cheap to test, but the factory is only
credible if the thing that judges the change cannot be edited by it. These rules make the gate
trustworthy; they are enforced by the engine, not requested from the model.

**Trusted base.** Policy, flow definitions, scenarios, review rules, reliability checks and risk
rules are loaded from the base commit or a trusted checkout, never from the worktree under test. The
verifier process and its dependencies run from a separate image or installed copy. Changing a check
is a separate task with its own plan, proof and approval; it can never ride along with the change it
judges. This matters most in dogfooding, where the change and the factory share one repository.

**Exact commit.** A verifier result, challenger verdict or human approval names the commit it was
given for. Any new commit invalidates all three and the gate runs again. The merge is checked at the
exact SHA being merged, not at the branch tip that was reviewed earlier.

**Risk rating and code owners.** A separate risk step rates each change `low`, `medium` or `high`,
rounding up when unsure, from the diff, touched paths, blast radius, reversibility, test coverage and
recent incidents. The rating never replaces the two human gates; it decides what evidence and who
the release gate needs:

| Risk | Release gate |
|---|---|
| `low` | one owner decision, with the proof and the verifier verdict already prepared |
| `medium` | one owner decision plus a second reader for the proof |
| `high` | named code owner, second reviewer, deeper verification, explicit rollback plan |

Code owners always approve `auth/`, `billing/`, migrations, secrets, CI/deploy configuration and
public API contracts, regardless of risk. LAIX consumes the rating as its `risk` input and returns
`requires_approval`; it still cannot open the gate.

**Observe before enforce.** Every new policy rule, flow node, risk rule and review check has three
modes: `off`, `observe`, `enforce`. Observe records `would_block` events and the reason; a rule is
promoted only after its false positives are reviewed. LAIX's shadow mode is one instance of this
rule, not a special case.

**Run the change.** Verification is not only a test run. A `preview` node boots the product, drives
one user path, and attaches the screen, log and trace to the proof. A per-product `verify` command
is versioned, kept fast and stress-tested like production code. Property tests cover invariants;
differential tests compare the old and new system on the same generated or sampled inputs for
migrations and refactors. Cheap checks run before expensive ones, and the builder runs tests, build
and lint before proposing.

**Bounded repair and flaky tests.** A failing check gets at most three repair rounds; after that the
task stops with `question.md`: what was tried, the evidence, the leading hypothesis and the options.
A test that passes only on retry is a defect, not a green result. The factory never skips, sleeps or
retries a flaky test to green; it records a flake, assigns an owner and either fixes it or deletes it
with a written reason.

**Review the reviewers.** The verifier, challenger and risk step are evaluated against historical
incidents and reverts, with a size-matched clean control so false positives are visible. Track recall,
false-positive rate and importance (`must-fix`, `should-fix`, `nit`); a technically correct finding
that no owner would act on is noise. Do not stack reviewers: tune the primary and give later rounds
the context of earlier failures.

**Comprehension debt.** Tests can stay green while nobody understands the code. The proof records
whether a person can explain the change: every high-risk change, and a sample of the rest, gets a
short written explanation from a person, not the builder. If they cannot explain it, the change
blocks and the plan is revisited. A versioned context pack — repo map, architecture notes, glossary,
past decisions and examples of good changes — is part of the builder's input and its hash is
recorded in the run.

**Friction and cleanup.** The engine records where agents stall, where review finds the same class of
problem and where changes need rework, per area of the codebase. A friction map compares each area
with a typical change of the same size and produces a brief: evidence, likely cause, bounded cleanup
and the test that keeps it fixed. Cleanup runs as its own task, never as an unreviewed drive-by.

**Operations.** Release ships with a health check, a stable window and a one-call rollback; a noisy
signal must not roll back every production pool. The supervisor has a stop switch that halts new work
and leaves running tasks resumable. A line you cannot stop is not a factory.

### 6.9 Agent readiness and the trust pyramid

The codebase is the agent's largest input. Agents copy what is already there — including workarounds,
deprecated patterns and comments that justify a shortcut. The order of investment follows the trust
pyramid from Lauren Tan's SpaceX SI talk (`docs/archive/reviews/review-5-slop.md`):

1. **Deterministic code**: API design, architecture, refactoring, lint rules, type systems,
   compilers, structural tests.
2. **Verification**: runtime checks, property-based tests, formal methods where they fit.
3. **Prose**: rules, skills, `AGENTS.md`, comments. Useful, but the weakest layer.

**Readiness before autonomy.** Before a flow runs on a repository, `works readiness` checks lint,
format, types, the fast test path, architecture boundaries, known suppressions and the presence of a
`verify` command and feature map. A red readiness gate refuses automation; the next task is the
missing check, not another prompt. A repo that produces slop at the inner loop produces more slop
when automated.

**Every correction becomes a check.** When a reviewer, challenger, escape or incident finds a
repeated problem, the fix is a deterministic check, a structural test or a better API — not a
comment or a new line in `AGENTS.md`. Existing occurrences are cleaned up in the same change or a
linked cleanup task. A suppression (`# noqa`, `# type: ignore`, `eslint-disable`, `skip`, `xfail`)
needs an owner, a reason and an expiry; it is a suspicious change, not a silent pass.

**Feature map and runtime artifacts.** A versioned `features/<product>.yaml` lists features from
the user's point of view: id, path, selectors or command, expected observation. A `preview` node
boots the product, drives the feature and attaches a screenshot, video, log and trace. The proof
shows which features were exercised and which were not. Review reads artifacts, not every diff.

**Architecture guardrails.** Import boundaries, dependency-graph rules, module fan-in and structural
tests live in the repository and run deterministically. They remove a class of review comments
instead of asking a model to remember it.

**Verification cost is visible.** The run splits builder, challenger and verifier tokens/USD. In a
mature line verification is often the largest share; that is a measurement, not a failure.

**Formal methods are a layer, not a silver bullet.** TLA+ for critical user flows, Lean for
algorithms and property-based UI testing are optional high-risk checks. They are never a substitute
for the verifier, the feature map or the two human gates. Auto-merge remains out of scope until
readiness, evals and a green escape window hold.

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
demo in `docs/archive/demo-m0.md`._

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

- [x] **T1.1** Scenario loader/validator with weights and P0/P1. **M**
- [ ] **T1.2** Scenario set for the R3 issue: at least three P0, written before build. **M**
  - Criteria: every P0 fails on the base commit.
- [ ] **T1.3** Repo adapter: clone/reuse, base commit pinned, dirty tree refused. **M**
- [ ] **T1.4** Worktree manager, symlink and `..` escape refused. **M**
- [x] **T1.5** Harness adapter: events → trace, model id recorded, cost per attempt. **L**
  - Done 2026-11-21: `LiveHarness` records a compact event trace in `harness.json`, model/provider
    on the run, and tokens/USD from the terminal result. Live fixture run: 104 563 tokens,
    $0.093938, `proved`.
- [ ] **T1.6** Reproduce step: agent writes a failing test; the runner verifies it fails on base. **L**
- [x] **T1.7** Plan drafting, scenario ids in the spec, gate 1. **M**
- [ ] **T1.8** Build with bounded repair: at most three rounds, then `needs_person` with
  `question.md` (what was tried, evidence, hypothesis, options). **M**
- [ ] **T1.9** Command runner: timeout, process-tree kill, path escape check, network policy. **M**
- [x] **T1.10** Evidence v1 computed: diff stat, test deltas, commands, exit codes, cost. **M**
  - Done 2026-11-21: diff, commands, exits, policy, cost and proof hash; the dedicated test-delta
    and suspicious-change list remains T1.11.
- [ ] **T1.11** Test-delta and suspicious-change list on the proof; gate refuses auto-allow while
  non-empty. The list flags new `# noqa`, `# type: ignore`, `eslint-disable`, `@ts-ignore`,
  coverage pragmas, `skip`/`xfail`, comments that justify a workaround, new timers and architecture
  bypasses. A suppression needs an owner, a reason and an expiry. **M**
- [ ] **T1.12** Supervisor resume: kill mid-run, restart, continue from the last event. **M**
- [ ] **T1.13** Two of three candidate issues complete end to end. **L**
- [x] **T1.14** Prompt registry: every step prompt is a versioned file under
  `flows/<flow>/prompts/`, rendered with safe substitution, hashed, and written to the run/proof.
  A prompt change without a benchmark run is refused by review. **S**
  - Done 2026-11-21: `flows/fix-issue/prompts/build.md`, `works.application.prompts`, hash in `harness.json`
    and the proof; `$` in issue text is not re-interpreted.
- [x] **T1.15** Structured findings: a `finding` event (`summary`, `evidence_refs`, `confidence`,
  `uncertainty`) that survives outside the agent context; the proof has “What we know / What
  remains uncertain”. No free-text parsing. **M**
  - Done 2026-11-21: `Finding` record, `works finding add/list`, proof Findings and Residual risk.
- [x] **T1.16** Attention metrics: `works metrics` derives human gate touches, waiting time,
  agent-hours per human-hour, runs without intervention, rework and fix share from events; never
  from agent self-reports. **M**
  - Done 2026-11-21: `works metrics` reports tasks, human touches, waiting, runs without human,
    median duration, tokens and USD from events and the ledger. Agent-hours need the dispatcher;
    they arrive with T3.10.
- [x] **T1.17** Proof quality rubric: a golden check that an engineer unfamiliar with the run can
  answer what changed, why, what proves it, and what remains risky. **S**
  - Done 2026-11-21: golden page plus a heading/rubric test for verdict, findings, commands,
    change, policy, residual risk and cost.
- [ ] **T1.18** Brand and mascot: Mira’s SVG source, avatar, voice and empty/waiting/proved/blocked
  poses; used in CLI human empty states and the future window, never in JSON or error text. **S**
  - 2026-11-21: primary and avatar assets, voice/usage rules, CLI empty state. Waiting/proved/
    blocked poses land with the GUI after M1.
- [ ] **T1.19** LAIX decision port: optional `DecisionPort` with a `LaixGate` adapter for plan and
  release; shadow mode logs disagreements before it can change a transition; decision JSON,
  `decision_id`, `trace_id`, `reason_code`, `confidence` and `alternatives` go into the event store
  and the proof. Deterministic gate remains the fallback. **M**
  - Criteria: path deny wins before LAIX; a missing/invalid decision falls back, never opens a gate;
    shadow differences are recorded for 20 cases.
  - 2026-11-21: `DecisionPort`, `DeterministicGate`, `LaixGate`, `ShadowGate` and
    `works decision replay --cases fixtures/decision-cases.jsonl`; the fixture has 20 cases.
    Actual LAIX historical replay and opt-in remain T2.14.
- [ ] **T1.20** Risk rating and code owners: a separate risk step rates each change
  `low | medium | high` from diff, paths, blast radius, reversibility, coverage and recent
  incidents, rounding up when unsure. Code owners always approve `auth/`, `billing/`, migrations,
  secrets, CI/deploy and public API. LAIX consumes the rating as `risk`. **M**
  - Criteria: the rating is recorded in `run.json` and the proof; it changes the evidence and the
    reviewers, never the existence of the two gates.
  - 2026-11-21: rating, owners, `required_reviewers` and `deeper_verification` are recorded and
    shown by `works risk`; release-gate enforcement is still open.
- [ ] **T1.21** Trusted-base checks and exact-commit binding: policy, flows, scenarios, review rules
  and risk rules load from the base commit or a trusted checkout, never the worktree. A new commit
  invalidates the verifier result, challenger verdict and approval; the merge re-checks the exact
  SHA. **M**
  - Criteria: a worktree edit to a check is refused; a commit after approval cannot merge on the old
    verdict; `checks_sha` is recorded in the run and proof.
  - 2026-11-21: base flow/check loading, `checks_sha`, approval commit binding and a separate
    `check-change` task kind; the trusted verifier image remains M2.
- [ ] **T1.22** Observe mode for every gate: `off | observe | enforce` for policy rules, flow nodes,
  risk rules and review checks; observe records `would_block` with a reason. Promotion happens only
  after false positives are reviewed. **S**
  - Criteria: a new rule can run for 20 changes without changing a transition; its false positives
    are listed from events.
  - 2026-11-21: policy, node and risk modes plus `works gate report`; review checks arrive with
    T2.17.
- [ ] **T1.23** Flaky-test policy: a test that passes only on retry is a defect, never a green
  result. No skip, sleep or retry-to-green; a `flake` event carries an owner and expiry, and the test
  is fixed or deleted with a written reason. **S**
  - 2026-11-21: `works flake add/list`, active flakes block the verdict with `flaky_test`, and the
    engine never retries a scenario to green.
- [x] **T1.24** Read-only GUI preview: queue, task detail, proof, risk, decision, `would_block`,
  readiness and feature coverage in one window; `works ui --read-only`; no write actions. **M**
  - Done 2026-11-21: `works ui` serves a dark/light, keyboard-first preview from the queue and run
    artifacts; API is GET-only, POST returns 405. Story is the default and only human reading, with
    a gray Reported origin and five Mira stops (Picked up, Confirmed, Fixed, Checked, Delivered),
    four stop states, full-body Mira at the current stop, a receipt strip and a specific blocked
    rail; the 10-step technical line lives in Evidence; replay sits behind “How we got here”;
    Present mode, human status labels, Needs you/In progress/Queued/Done groups, `Ctrl+K` palette
    and deep links. Demo uses Firefox, LibreOffice, GIMP, Blender and Joplin, including a task in
    the middle of the check. The full React/Vite window, SSE and Playwright are later.
  - 2026-11-22: added the Release view (packet, gate 2, delivery, confirmation, team, verifier,
    LAIX shadow), inline artifacts and before/after images, product map, detector panel,
    `--write` actions, a full new-task form, GitHub/Jira/detector intake, timeline filters, queue
    product/source filters and a release-aware Story. Still local, vanilla JS and polling.
  - 2026-11-23: added the Thread view: event-sourced roles and cards, a right rail, add-context,
    and a real openjiuwen-backed `Ask Mira` with SSE streaming and `thread.agent` recording.
    The assistant is advisory and cannot open a gate.
  - 2026-11-23: worklog questions with recommended actions and `Open run`, a merged Tell Mira
    composer, AI commentary for builder/inspector/reporter, run history and comparison, a Factory
    metrics/ledger dialog, export links, artifact lightbox and before/after slider, settings,
    and an event drawer.
  - 2026-11-23: added an advisory `Team discussion` layer: the model writes inspector, challenger
    and reporter messages with a support / concern / block stance, stored as `thread.discussion`
    and labelled AI text. It cannot change a verdict or open a gate.
  - 2026-11-23: Ask Mira now carries the last three recorded question/answer pairs, so the
    composer behaves like a worklog conversation without inventing memory outside the record.
    Every model answer is labelled `AI answer` and AI text renders safe bold/code instead of raw
    markdown. A client that navigates away no longer turns a closed socket into a server traceback.
  - 2026-11-23: New task opened as a Claude-style prompt with exact fields under Details. The local
    draft reads a reference, product, repository and title from the text; the person still presses
    Create task, and no run or gate starts.
  - 2026-11-23: P0 session pass from the design critique: centered 264 / 760 / 288 workspace,
    one identity row per turn, 15.5px body, collapsed Review block, a top decision bar with the
    human gate, a one-row composer, and a Decision / Next / Run / People rail. Session replaces the
    Thread tab label; `/thread` stays the deep link.
  - 2026-11-23: full-height shell: 52px app bar, 280px queue, 980px session pane with a 760px
    measure and a 340px context pane. The pane owns the title/tabs; Plan / Build / Check / Release
    chapters collapse past work and open the current one; Full log expands; Review collapses agent
    discussion; one decision card.
  - 2026-11-23: one content frame for every view and a near-white surface system. Session now reads
    the whole run as one conversation: the person's report on the right, then pipeline phases with
    quiet dividers, inline plan/release question cards, a plan/blocked decision card, a collapsed
    Review block and technical rows behind Details. The rail stays at the right edge; the
    conversation measure is 900px; Run log reuses the same column with a compact chapter bar.
  - 2026-11-23: Session controls are unambiguous: a two-tab Conversation / Run log switch, a
    separate Ask AI group for Review and Commentary with busy states and a return to
    Conversation, and an All chapters checkbox in Run log (no more Digest / Full log labels).
  - 2026-11-23: the GUI moved to React/Vite (`web/`) with SSE `/api/events` for the queue and the
    open task; `Ask Mira` keeps its token stream. Thread is now a session pane with right-aligned
    user turns, left-aligned labelled AI answers, a docked composer and auto-follow. Story keeps the
    wave route; `j`/`k`, `t`, `?`, `c` and `?at=` deep links are ported.
- [ ] **T1.25** Verification cost split: builder, challenger and verifier tokens/USD in `run.json`
  and the proof; verification share is reported next to the total. **S**
  - 2026-11-23: `builder_tokens`, `builder_usd`, `verifier_tokens`, `verifier_usd` and
    `verification_share` are recorded and rendered in the proof. The JiuwenSwarm adapter now reads
    provider usage metadata as well.
- [x] **T1.26** PPMA memory backfill: `works memory backfill` reports already-finished runs from
  `runs/*/run.json` and `evidence.json` without re-running the factory; newest first, `--dry-run`,
  per-run failures, idempotent ULIDs. **S**
  - Done 2026-11-21: verified against `ppma serve --profile fake --auth dev`: three demo runs
    accepted on `POST /v0/spaces/me/messages`; a run without evidence is skipped, not failed.
    Each send records `memory.reported` (or `memory.failed`), and Story/Evidence show the honest
    memory status; a second backfill does not duplicate the local event.
  - Still open: automatic PPMA E2E in CI and recall (T2.21).
- [x] **T1.27** GUI report intake: `works ui --write`, `POST /api/tasks`, a `+ Report a bug` button
  in the task list context and a form that creates only a `queued` task. **S**
  - Done 2026-11-21: local-only POST, `X-Works-Write` header, repo/.git/ref/title validation,
    duplicate source returns the existing task, read-only mode still returns 405. The button is
    hidden unless write mode is on; no run or gate is started from the form.

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
- [x] **T2.9** Evidence v2: verdict, failures, cost, **what was not tested**. **M**
  - Done 2026-11-21: proof has Findings, Challenge, Residual risk and an explicit not-tested list.
- [x] **T2.10** Adversarial challenge: a separate session, on a different provider where possible,
  tries to disprove the diagnosis and then the fix; the verdict is recorded and a send-back blocks.
  **M**
  - Done 2026-11-21: separate challenger prompt/session, own disposable worktree with the builder
    diff applied, JSON verdict, fail-closed; `challenge.json`, proof section and a blocking fake
    trace. Live run: challenge ALLOW, 88.6 s, 180 604 tokens, $0.192889. Provider split still T2.3.
- [ ] **T2.11** Agent eval suite: backtest past runs with the answer stripped; score investigation
  and handoff separately; refuse cases whose metrics/traces would leak the cause; scan transcripts
  for spoilers. **L**
- [ ] **T2.12** Summary grader: snapshots of saved tasks scored by a separate grader for
  “understandable to an unfamiliar engineer”, kept charts and evidence-backed next step. **M**
- [ ] **T2.13** Service identity: the verifier and builder run under scoped identities; every
  action is attributable to a run, not to the developer’s user. **M**
- [ ] **T2.14** Decision quality: install the pinned `laix==0.18.0` from the local checkout (the PyPI
  `laix` name is an unrelated `0.0.0` placeholder), run 20 historical gate cases through real LAIX
  and the current deterministic rule; compare verb, approval and reason code; any case where LAIX
  allows what the policy or verifier refuses is a defect in the adapter, not a policy change.
  Adapter tests with a fake `LaixGate` are necessary but not enough; CI and docs must show the real
  package. **M**
  - 2026-11-22: installed the local `laix==0.18.0` checkout and ran the 20-case replay:
    **1/20 agreement, 0 unsafe allows**. LAIX is conservative and not safe to opt in; the adapter
    alternatives handling was fixed for the current API. Opt-in remains open.
- [ ] **T2.15** Run the change: a `preview` node boots the product, drives one user path and attaches
  screen, log and trace to the proof; a per-product `verify` command is versioned, fast and
  stress-tested. Cheap checks run before expensive ones. **M**
- [ ] **T2.16** Property and differential tests: invariants for the changed domain; old and new
  systems compared on generated or sampled inputs for migrations and refactors. **M**
- [ ] **T2.17** Review the reviewers: evaluate verifier, challenger and risk step on historical
  incidents and reverts with a size-matched clean control; track recall, false positives and
  importance. Stamp every commit `verified: none | unit | integration | e2e | manual`. **M**
- [ ] **T2.18** Agent readiness and architecture guardrails: `works readiness` checks lint, format,
  types, the fast test path, architecture boundaries, known suppressions, `verify` and a feature
  map; a red gate refuses automation. Import boundaries, dependency graph and structural tests run
  in the verifier. **M**
  - 2026-11-21: `.works/readiness.yaml`, `works readiness`, exact suppression audit, feature-map
    presence, `EXIT_BLOCKED` red gate, `readiness.checked` event, run-time refusal for configured
    repositories, and the Evidence panel are in. Live runs now require a green gate even without a
    config; the Evidence panel can run the checks in `--write` mode. The readiness report also
    carries the internal import graph and fails on import cycles. Open: container-level verifier
    isolation, provider split and review-the-reviewers.
- [ ] **T2.19** Feature map and runtime artifacts: versioned `features/<product>.yaml` with id, user
  path, selectors or command and expected observation; `preview` attaches screenshot, video, log and
  trace; proof shows covered and uncovered features. **M**
  - 2026-11-21: schema, loader, validation, readiness content check, proof-scenario coverage and the
    Evidence covered/failed/not-covered panel are in. Open: preview attaches screenshot/video/log/
    trace and executes selectors or commands at run time.
- [ ] **T2.20** Real-mode acceptance: one pinned, small OSS repository with a known bug and a
  failing scenario; an opt-in `--live` openjiuwen run with a token/USD budget cap produces a proof
  and a release dry-run. The default CI stays deterministic and free; this job proves the real path,
  not only the fixture. **M**
- [ ] **T2.21** Memory before interruption: PPMA recall of similar past failures and decisions is
  offered to the planner before any question reaches a person; every recall is recorded. Without a
  reachable PPMA the run continues and says “memory unavailable”. Moved up from T4.8 because recall
  is the point of the memory product, not a late add-on. **M**

- [ ] **T2.22** agent-core verification team: inspector, challenger and reporter on `BaseTeam` +
  `TeamRuntime`, model-free, reading recorded evidence only; the team cannot open a gate. **M**
  - 2026-11-22: `works team verify` runs the three roles in agent-core's own Python via subprocess,
    records `team.verified`, and returns `allow` or `block`. The container adapter is T2.25; the
    provider split and a live daemon in CI are still open.
- [ ] **T2.23** Signal intake: GitHub Issues, Jira and firing detector alerts become ordinary queued
  tasks with the same `(kind, ref)` deduplication; HTTP is behind an injectable transport so tests
  never touch the network. Live private-repo runs need credentials. **S**
  - 2026-11-22: `works source github`, `works source jira` and `works source detector` are in;
    Alertmanager, generic and NDJSON payloads are parsed, resolved alerts are ignored, and a named
    detector lives in `.works/detectors.yaml`. A live private tracker remains open.
- [ ] **T2.24** Product-to-repository map: `.works/products.yaml` resolves `--product` without a
  repeated `--repo`, keeps `--repo` as the override, and fails with the known product names instead
  of guessing. **S**
  - 2026-11-22: `products.py`, the submit/UI wiring and edge-case tests are in.
- [ ] **T2.25** Verifier isolation: `--verifier docker` runs scenarios and checks with no network,
  dropped capabilities, read-only scenarios and only the worktree mounted; a missing daemon is a
  configuration error. **M**
  - 2026-11-22: Docker argument builder, path/env rewriting and `works doctor` daemon status are in,
    tested through a recorded runner. The process verifier drops builder credentials, `works doctor`
    warns on a shared key, and Evidence records the verifier name and isolation. A live container
    test now runs in CI (`tests/integration/test_docker_live.py`); local runs need a running daemon.
- [ ] **T2.26** JiuwenSwarm boundary: `works.swarm.v1` request/result contract, an isolated
  `SwarmHarness`, `works swarm doctor` and `works run --swarm`; no fake fallback. **M**
  - 2026-11-22: adapter and preflight are in and tested. The local checkout now starts; the
    `agent_gateway` import problem is gone.
  - 2026-11-23: `scripts/swarm_adapter.py` is the default entrypoint. It drives the JiuwenSwarm
    chat CLI, returns the worktree diff or a read-only challenge verdict, and is tested end to end
    on a fixture with a fake CLI. A live model run still needs the gateway configuration.

### M3 — Release, return, escape (weeks 7–8)

- [x] **T3.1** Release gate: normalized path matching, deny-wins, approval bound to commit hash. **M**
  - 2026-11-22: `works release` builds a read-only packet bound to run, base commit and proof;
    `works approve --gate release` opens gate 2, moves `proved → releasing → released`, records the
    gate event and `release.json`, and is idempotent per commit. Nothing is published by the gate.
- [ ] **T3.2** Publish asserts that the delivered commit matches the approved proof; otherwise
  re-gate. **S**
  - 2026-11-22: delivery verifies the worktree diff hash and staged file list against the proof
    before committing. A real remote push is covered by a local bare-repo test; a live GitHub run
    still needs a token.
- [ ] **T3.3** Branch + PR with proof, `Works-Run:` trailer, bot identity. **M**
  - 2026-11-22: `works deliver` creates `works/<task-id>`, commits with the trailers, pushes to
    `origin`, and with `--provider github|gitlab` opens one pull or merge request. Idempotent by
    branch, commit and run marker. Live creation needs the matching token.
  - 2026-11-23: `works deploy` runs the owner-approved deploy command (or the product map's
    `deploy:`) on the delivered commit, with a dry run, `deployment.json`, a `deploy.finished`
    event and idempotency. Production credentials and rollback stay operational.
- [ ] **T3.4** Return: one comment per run on the source issue, idempotent. **M**
  - 2026-11-22: delivery and confirmation both write one marker comment per run to GitHub, GitLab
    or Jira. `--close` closes a GitHub/GitLab issue or transitions Jira to Done. Live calls need
    the matching token.
- [ ] **T3.5** Confirm: re-run the reproduction; result recorded. **M**
  - 2026-11-22: `works confirm` runs an HTTP check, an explicit command, or the plan's scenario set
    against the delivered commit in a fresh worktree; the result is `confirmation.json` plus a
    `confirmation.finished` event. `--preview` supplies an optional Playwright driver; a live
    browser install remains.
- [ ] **T3.6** **Escape detection**: arm a 14-day window per release; a revert, hotfix or red main
  touching the same paths attributes a row to the release. **L**
  - 2026-11-23: `works escapes` scans local git history for reverts and hotfixes on the released
    paths and records repeated-source rework; `escapes.json`, `escape.detected`, `rework.detected`
    and metrics counts are in. A remote main/CI feed is still open.
- [ ] **T3.7** Revert path: revert PR, note, post-mortem, ledger row. **M**
- [ ] **T3.8** Human minutes from gate timestamps. **S**
- [x] **T3.9** Waiting states and wake subscriptions: `waiting_review`, `waiting_ci`,
  `waiting_deploy`; a PR comment, CI result, deploy or issue update wakes the task instead of
  making it terminal. **L**
  - Done 2026-11-21: `Queue.wait/wake/expire_wait`, stored wake event, deadline and default;
    `works wait` / `works wake`; wrong events refused; projections replay.
- [x] **T3.10** Dispatch loop: `works dispatch` claims ready tasks, advances one step, releases,
  and is safe to kill; no task is run twice. **L**
  - Done 2026-11-21: one-pass dispatcher with `O_EXCL` claims, `--limit`, `--watch`, per-task
    errors and a JSON/human report; two dispatchers cannot own one task. Real forge/CI webhooks
    are still pending the ports.
- [ ] **T3.11** Clean-environment matrix: tests on clean Windows, macOS and Linux (or the supported
  subset), with no developer state. **M**
- [ ] **T3.12** Merge-result re-check: after a branch lands, CI runs on the merged result; two green
  branches may not break `main`. **S**
- [ ] **T3.13** Post-release confirmation beyond reproduction: the live metric, download or issue
  signal improves; a partial recovery opens a new task with a new cause. **M**
- [ ] **T3.14** Incident linking: one defect reported through several sources is one task with
  linked refs, grouped by product metric and ranked by impact. **M**
- [ ] **T3.15** LAIX commitments: release and return promises (`approved commit`, `CI green`,
  `return to issue`) enter a `CommitmentGraph`; a hard violation becomes `verify` or `ask`. Path
  deny and the verifier remain authoritative. **M**
- [ ] **T3.16** Safe operations: release carries a health check, a stable window and a one-call
  rollback; a noisy signal cannot roll back every pool. `works stop --all` halts new work and leaves
  running tasks resumable. **M**
- [ ] **T3.17** Performance budget: startup, interaction and key-flow latency are scenarios with a
  declared budget; a regression blocks the proof and is attributed to the release. **M**

**Demo M3:** issue → merged PR → proof → comment → green reproduction; then a forced revert attributed
to its release.

### M4 — Second flow, learning, benchmarks (weeks 9–10)

- [ ] **T4.1** `docs.yaml`: documentation flow, automatic release only after T3.6 is green. **M**
- [ ] **T4.2** Routing from the signal, not a flag. **M**
- [ ] **T4.3** Scorers: rubric on a 25% sample, separate from the verdict. **M**
- [ ] **T4.4** Benchmark suite: five past tasks replayed at their initial state. **L**
- [ ] **T4.5** Prompt/model comparison using the benchmark before any change is adopted. **M**
- [ ] **T4.6** Learning loop: every repeated finding, escape or revert becomes a deterministic check
  — lint rule, structural test, API change or scenario — as a reviewed PR; old occurrences are
  cleaned up in the same change or a linked task. Never automatic, never a "next time" comment. **L**
- [ ] **T4.7** In-scope rate measured on new issues; report next to the metrics. **S**
- [ ] **T4.8** Memory before interruption — the first recall slice moved up to T2.21; M4 keeps
  lesson extraction, calibration and memory-quality benchmarks. **M**
- [ ] **T4.16** Orbit publish adapter: optional, owner-approved publishing of a proof to a team
  room through a contract; never a second source of truth, never automatic. **M**
- [ ] **T4.9** Self-repair: a daily scan of run logs finds repeated tool/permission failures and
  opens a bounded repair task; the fix is reviewed like any other. **M**
- [ ] **T4.10** Attention dashboard: cost and time per released fix, human touches, waiting time,
  fix share and rework reported together; agent count is never a target. **M**
- [ ] **T4.11** Delivery loop: every adopted rule, prompt or model change is evaluated on the
  benchmark before and after; a regression reverts it. **M**
- [ ] **T4.12** Attention inbox: waiting tasks and gate requests are ranked by LAIX
  `AttentionScheduler` with a human-attention budget; `works attention` and the GUI show selected
  and deferred decisions, not a flat queue. **M**
- [ ] **T4.13** Decision outcomes: gate decisions, reversals and overrides feed LAIX calibration;
  a calibration report is shown next to attention metrics, and a drift beyond the agreed band
  reopens the policy. **M**
- [ ] **T4.14** Friction map and cleanup loop: per-area stall, review rework and repeated-finding
  rate, compared with a size-matched typical change; a brief with evidence, cause, bounded cleanup
  and a keeping test. Cleanup runs as its own reviewed task. **M**
- [ ] **T4.15** Comprehension sample and context pack: every high-risk change and a sample of the
  rest get a short human explanation in the proof; a versioned repo map, architecture notes,
  glossary, decisions and good examples are hashed into the run. **M**

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
decision:
  provider: laix          # off | shadow | laix
  mode: shadow            # shadow until T2.14 passes, then per-gate opt-in
  fallback: deterministic
  attention_budget: 3     # human decisions per day in the inbox
verification:
  trusted_base: true      # checks, scenarios, review rules from the base commit
  bind_to_commit: true    # a new commit invalidates verdict, challenge and approval
  default_mode: observe   # off | observe | enforce for every new gate
  repair_rounds: 3        # then blocked with question.md
risk:
  rating: computed        # low | medium | high; round up when unsure
  owners:
    auth: [owner]
    billing: [owner]
    migrations: [owner]
    secrets: [owner]
    ci: [owner]
    public_api: [owner]
budget: {tokens: 400000, usd: 10, wall_minutes: 60, ci_minutes: 30}
```

Rules: segments normalized before matching; deny wins; `..` rejected; auto-allow refused while the
suspicious list is non-empty; approval is bound to the commit and re-checked at publish. When
`decision.provider` is `laix`, LAIX may change *which* gate applies only after path policy and never
in place of the verifier; an invalid decision falls back to the deterministic rule (§6.7). A new
commit always invalidates the previous verdict and approval. Risk decides who and what evidence the
release gate needs, never whether the gate exists; code owners always approve their paths.

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
| Human touches | gate decisions + steering messages per release | < 3 |
| Waiting time | time in each waiting state, p50/p95 | reported |
| Agent leverage | agent-hours per human-hour | reported, rising |
| Runs without intervention | runs with no human message | reported, rising |
| Rework | fixes that reopen, revert or fail confirmation | < 10% |
| Fix share | fix commits / all commits | falling |
| CI failure rate | red runs / all runs on `main` | < 5% |
| Escapes | attributed within 14 days per 100 releases | < 5 |
| Cost | USD per release, verifier included | < $15 |
| In-scope rate | share of new issues the flow can take | reported, not targeted |
| Decision fallback rate | gate decisions that fell back to the deterministic rule | reported, < 10% |
| Shadow disagreement | plan/release cases where LAIX and the deterministic gate differ | reported, reviewed |
| Gate override rate | human decisions that reverse the engine's recommendation | reported, falling |
| Decision latency | p50/p95 time spent in `DecisionPort.decide` | < 250 ms p95 |
| Attention fit | scheduled decisions that fit the configured attention budget | 100% |
| Shipped changes | released changes per week, by flow | reported, rising |
| Revert rate | reverts / releases, split by risk and approver | falling |
| Review latency | ready-for-review → first decision, p50/p95 | falling |
| Review effort | human minutes per accepted change | falling without more escapes |
| Cost per accepted change | tokens, compute and human time / released change | falling |
| Comprehension sample | sampled changes a person can explain in three sentences | rising or stable |
| Risk calibration | risk rating vs actual reverts and escapes | reported, reviewed |
| Check false positives | observe-mode blocks a reviewer judged wrong | falling before enforce |
| Readiness | repositories that pass `works readiness` / repositories onboarded | 100% before automation |
| Feature coverage | features exercised by scenarios / features in the map | rising, reported |
| Verification cost share | verifier tokens and USD / total run cost | reported, not targeted |
| Suppression delta | new `noqa`/type-ignore/skip/xfail per accepted change | falling |
| Architecture checks | pass rate of import and structural checks | 100% |
| Performance budget | scenarios within their declared latency budget | 100% |
| Suspicious changes | flags per 100 accepted changes | falling |

---

## 14. Testing

- Unit: state machine, policy table (adversarial paths), scenario loader, evidence computation.
- Property-based: state machine and path policy with hypothesis (unicode paths, `..`, symlinks).
- Contract: harness adapter against recorded traces; no live model in CI.
- Golden files: evidence rendering, so a page change is a reviewed diff.
- Integration: fixture repo + fake harness, the whole loop in CI.
- Mutation and sneaky-patch suites in CI; mutation ≥ 70% on core.
- Agent evals: past tasks replayed with the answer stripped; investigation and handoff scored
  separately; transcripts checked for spoilers; saved task snapshots used as stable backtests.
- Leak test: grep every builder-readable artifact for scenario strings.
- Clean-environment matrix: Windows, macOS and Linux (or the supported subset), no developer state.
- Merge-result re-check: CI runs again after the branch lands.
- Load: 10 000 tasks in the queue; `status` under 100 ms.
- Performance: CLI start, evidence render and report timed in CI; fail on > 20% regression.
- LAIX conformance: the pinned contract is exercised against recorded `DecisionRequest` fixtures;
  golden decisions compare verb, reason code, approval and alternatives. Adapter tests assert that a
  denied path is never admitted, a missing/invalid decision falls back, and a `wait` never advances.
- Decision replay: T2.14 replays 20 historical gate cases; a case where LAIX allows what policy or
  the verifier refuses fails the build. Shadow differences are stored, not inferred.
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
| Builder grades itself | Separate challenger and verifier roles; provider split; no self-reported done |
| Attention theater | Metrics derived from events, not agent prose; agent count is not a target |
| Waiting-state deadlock | Every wait has a wake event, a deadline and a default; `works doctor` shows stranded waits |
| Findings drift | Findings are append-only records with evidence refs; conflicting findings stay visible |
| LAIX pre-1.0 churn | Pin `0.18.0`, adapt behind `DecisionPort`, conformance fixtures; a contract bump is a reviewed change |
| Decision theater | Urgency, risk and uncertainty come from recorded evidence, never agent prose; decisions without evidence fall back |
| LAIX allows what policy denies | Path deny and the verifier run before/after the decision; adapter tests prove fail-closed; shadow review before opt-in |
| Attention starvation | Explicit `human_attention_budget`; deferred decisions stay visible with a deadline and a default |
| Self-modifying checks | Checks and review rules load from the trusted base; a check change is a separate task; exact-commit binding |
| Review bottleneck | Risk-rated approval and prepared proofs; measure review latency; do not skip review to clear the queue |
| Comprehension debt | Human explanation for high-risk and sampled changes; context pack; ownership map; architecture review |
| Verification theater | Review the reviewers on incidents and reverts with a clean control; validity and importance tracked separately |
| Flaky tests | No skip, sleep or retry-to-green; a flake event with owner and expiry; fix or delete with a written reason |
| Blocking-prompt stall | No interactive prompt in the engine path; a question becomes a wait with a wake event and a deadline |
| Non-idempotent action | Idempotency key on every external action; a retry never duplicates a merge, comment, release or task |
| Rollback misfire | One-call rollback, health check and stable window; a noisy signal cannot roll back every pool |
| Slop propagation | Readiness gate; every correction becomes a deterministic check; clean old occurrences, not only new ones |
| Readiness theater | Readiness checks are mechanical and sampled; a green checklist without architecture tests is a finding |
| Comment/rule escape hatch | Flag workaround comments and suppressions; an exemption needs an owner, a reason and an expiry |
| Verification cost blow-up | Split builder/challenger/verifier cost; cap per run; prefer deterministic checks and cached artifacts |
| Formal verification overreach | High-risk flows only; a layer, not a substitute for the verifier or the gates |
| Feature map drift | Versioned map, exercised in preview, reviewed with the proof; stale ids fail the scenario |
| Auto-merge too early | Two human gates until readiness, evals and a green escape window hold |
| Unbounded autonomy | Two human gates remain; autonomy expands only after evals and a green escape window |

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
- [x] **D8** Factory shape: a task state machine with a dispatcher and wake subscriptions, not an
  org chart of role-playing agents. Work decides its own shape.
- [x] **D9** No agent grades its own work: builders, challengers and verifiers are separate roles,
  preferably separate providers. A self-reported "done" is never evidence.
- [x] **D10** Attention is the primary metric: human touches, waiting time, agent-hours per
  human-hour and rework. Agent count is explicitly not a target.
- [x] **D11** Findings are structured records outside any agent's context; free-form agent prose is
  never parsed into a decision.
- [x] **D12** LAIX is the optional decision layer, not the executor, verifier or memory. It chooses
  `act / ask / wait / verify / escalate` at the plan and release gates and ranks attention; Works
  enforces policy, owns state and proves the result. Shadow first, then per-gate opt-in, pinned
  `laix==0.18.0` behind `DecisionPort`; a missing or invalid decision falls back to the deterministic
  gate. Path deny and the verifier remain authoritative. The LAIX app kit's execution, storage and
  delivery are not used.
- [x] **D13** Decisions consume recorded evidence only — reproduction, verifier, policy, budget,
  deadline, commitments — never agent-supplied urgency or free-form prose. Overrides, shadow
  disagreements, fallbacks and calibration are derived from events; an attention budget is explicit
  and a deferred decision keeps its deadline and default.
- [x] **D14** Checks outlive changes. Policy, flows, scenarios, review rules and risk rules are read
  from the trusted base, not the worktree; a change cannot edit the check that judges it. Every
  verdict and approval is bound to the exact commit and invalidated by a new one.
- [x] **D15** Risk-rated approval. A separate risk step rates each change `low | medium | high` and
  code owners always approve critical paths. The rating changes the evidence and the reviewers, not
  the existence of the two human gates; LAIX consumes it as an input.
- [x] **D16** Observe first, then enforce. Every new gate runs in `off | observe | enforce`, and the
  verifier, challenger and risk step are themselves evaluated on historical incidents and reverts
  with a size-matched clean control. Reviewers are tuned, not stacked.
- [x] **D17** Readiness before autonomy. Works refuses to automate a repository that fails the
  readiness gate: lint, format, types, fast tests, architecture boundaries, known suppressions,
  `verify` and a feature map. A red gate produces the missing check, not another prompt.
- [x] **D18** Every correction becomes a deterministic check. Repeated findings, escapes and
  reverts become a lint rule, structural test, API change or scenario, reviewed like code. Comments
  and rules are the weakest layer; a suppression needs an owner, a reason and an expiry.
- [x] **D19** Verification artifacts are the review unit. The proof carries feature coverage,
  screenshots, video, logs, traces and property/formal results where used. Formal methods are
  optional high-risk layers, never a substitute for the verifier or the two human gates.
- [x] **D20** One proof, two readings. Story is the default for a reporter, support or product;
  Evidence is one click away for an engineer. Both are computed from the same proof, and the human
  answer (changed, checked, not checked, who decides) lives in the Story hero and receipt strip;
  technical states and reason codes stay in Evidence.
- [x] **D21** The task is a line. Story is the default view: a gray Reported origin and five Mira
  stops (Picked up, Confirmed, Fixed, Checked, Delivered) with four states — not started, in the
  middle, done, stopped. Mira appears only at the current stop, never on future ones; the
  ten-station technical line lives in Evidence; replay comes from real events, and no animation is
  backed by anything but an event.

---

## 18. Definition of done

A milestone is done when the demo runs twice, the ledger has rows, the proof is readable without
narration, the limitations are written down, **the engineering standard in §6.4 holds for every
touched file**, and **the refactoring gate that follows it (§6.6) is closed**. A factory milestone
also passes the parity checklist: task state and findings survive outside the agent; waiting has a
wake event; no agent grades its own work; attention metrics come from events; the proof says what was
not tested; any LAIX decision is backed by recorded evidence and has a deterministic fallback; and
the gate that judged the change ran from the trusted base, was bound to the exact commit and had
passed observe mode; and readiness is green with the feature map exercised in the proof. The proof
also answers a reporter's question — “was my problem fixed?” — in the Story hero and receipt strip,
with Evidence one click away.

---

## 19. Not in this plan, on purpose

Detector ingestion, person channel beyond CLI, deploy/canary, web UI, multi-repo, multi-tenant.
Each has a sentence in §3 and no task. Also explicitly not planned: an org chart of role-playing
agents, a zoo of model providers before M3, and autonomous merge without the two gates.

---

## 20. Changelog

- **v4.24** — report intake and readiness execution: `works ui --write` adds a sidebar
  `+ Report a bug` form that creates only a queued task (local POST, header, repo/.git validation,
  duplicate idempotency), while read-only remains 405. Live runs now require a green readiness gate;
  Evidence can run the checks in write mode. The LAIX `decision` extra is declared, and the demo
  script falls back to an unlocked sibling workspace on Windows.
- **v4.23** — feature maps become evidence: versioned `features/<product>.yaml` with user paths,
  expected observations and scenario ids; the loader validates them, readiness fails on an invalid
  or empty map, and Evidence shows each feature as covered, failed or not covered by the proof.
  Preview artifacts and selector execution remain open.
- **v4.22** — the readiness gate: `.works/readiness.yaml`, `works readiness` with lint, format,
  types, fast tests, product verify and architecture commands, an exact suppression allowlist, a
  feature-map presence check, `EXIT_BLOCKED` on red, `readiness.checked` events, a run-time refusal
  for configured repositories, and the Evidence panel. Import-graph checks and map content remain
  open.
- **v4.21** — memory becomes visible and the preview becomes mobile-honest: runs record
  `memory.reported`/`memory.failed`, and Story/Evidence show “PPMA synced”, “PPMA failed” or “Not
  recorded” instead of a config badge. The route turns into a vertical list under 720 px with real
  per-milestone ARIA names; replay updates the route and receipt in place instead of rebuilding the
  page. Dead `lineMode`/`renderStoryStage` code is gone.
- **v4.20** — PPMA becomes a usable integration, not only a side effect: `works memory backfill`
  reports already-finished runs from `run.json` + `evidence.json` with a dry run and per-run
  failures, and was verified against a local PPMA fake profile (three demo runs accepted). Plan
  adds real-mode acceptance (T2.20), memory recall before interruption (T2.21, moved from T4.8),
  real LAIX replay in T2.14 and an optional Orbit publish adapter (T4.16).
- **v4.19** — the route becomes a journey: a gray **Reported** origin (not part of Mira's path)
  followed by five Mira stops, each with not-started / in-the-middle / done / stopped states and
  state-aware labels (“Mira is fixing it”, “Fixed”, “Mira stopped while fixing”). Adds a
  mid-check **Blender** demo task with the fix done and Mira checking; the demo now covers five
  open-source products. Pending stops lose empty timestamps and the route gets a state legend.
- **v4.18** — Story becomes the only human reading: five plain-language milestones (Reported →
  Confirmed → Fixed → Checked → Released), Mira at the current milestone only with sentence labels
  (“Mira confirmed it”, “Mira is ready to release”), full-body Mira never clipped or overlapping,
  a receipt strip replacing the Summary tab, “How we got here” replay, Present mode, a specific
  blocked rail, queue groups Needs you/In progress/Queued/Done, and one reported time shared by the
  header, hero and route. The ten-step technical line moves into Evidence.
- **v4.17** — Story polish: full-body Mira without a square background, prominent in the hero and
  on the current station; future stages dimmed; blocked “why it stopped” callout; human story
  artifacts; realistic demo on four products with spread event times; removed the empty “Mira is
  watching the queue” strip.
- **v4.16** — Story line: 5 human stations with Mira, 10-station technical line, replay scrubber,
  event-derived gates/artifacts, Cinema mode, deep links `?at=` and `?line=technical`; Story is the
  default view.
- **v4.15** — one proof, two readings: Summary/Evidence split in the preview, human status labels,
  Needs you/Working/Ready/Done groups, `⌘K` palette, deep links and run metadata; ADR-014 and D20.
- **v4.14** — read-only GUI preview: `works ui` serves the queue, task, proof, risk, decision,
  readiness and feature-map placeholders from events and run artifacts; dark/light, density,
  keyboard navigation and deep links; GET-only API.
- **v4.13** — trust pyramid and agent readiness from Lauren Tan's SpaceX SI talk: `works readiness`
  gate, feature map and runtime artifacts, architecture guardrails, suppression-aware suspicious
  list, verification cost split, performance budgets, correction → deterministic check (D17–D19,
  §6.9); T1.25, T2.18, T2.19, T3.17 opened.
- **v4.12** — group 1 of the gate hardening: `check-change` task kind and check-path refusal,
  flake enforcement (`flaky_test`), risk routing requirements, risk observe mode, `works gate
  report`, 20-case `works decision replay`, and a read-only GUI preview queued as T1.24.
- **v4.11** — gate integrity from the software-factory study: trusted-base checks, exact-commit
  binding, risk-rated approval with code owners, observe-before-enforce, run-the-change preview,
  property/differential tests, bounded repair, flaky tests as defects, review-the-reviewers,
  comprehension sample, friction map, safe rollback and stop (§4, §6.8, §9, D14–D16). T1.20–T1.23,
  T2.15–T2.17, T3.16, T4.14–T4.15 opened.
- **v4.10** — LAIX as the optional decision layer: `DecisionPort` with `LaixGate` for plan/release,
  decision events and proof section, attention routing, commitments deferred to M3; shadow first,
  deterministic fallback, policy and verifier authoritative (§6.7, D12–D13). Deck gains LAIX as a
  first-class integration citizen; T1.19, T2.14, T3.15, T4.12, T4.13 opened.
- **v4.9** — adversarial challenge: separate challenger session in plan mode, versioned
  `challenge.md`, JSON verdict (`allow/reason/concerns`), fail-closed parsing, `challenge.json`,
  proof Challenge section and a blocking fixture trace; T2.9/T2.10 closed.
- **v4.8** — waiting states and wake events (`waiting_review/ci/deploy`, deadline + default,
  replayable), `works wait/wake`, and `works dispatch` with claims, `--limit`, `--watch` and
  per-task reporting; T3.9/T3.10 closed.
- **v4.7** — first parity batch delivered: versioned prompt with hash, structured findings and
  `works finding`, attention metrics and `works metrics`, proof rubric with residual risk; Mira
  primary/avatar assets and CLI empty state. T1.14–T1.17 closed; T1.18 poses defer to the GUI.
- **v4.6** — brand: Mira, the magpie courier; primary and avatar SVG assets, voice and usage rules
  (`docs/design/strategy/mascot.md`); T1.18; Mira in empty/waiting/proved/blocked states, never as a chat
  avatar or status substitute.
- **v4.5** — factory parity from OpenAI Performance Factory and Alex Greenshpun's essay: waiting
  states and wake subscriptions; dispatch loop; structured findings; versioned prompt registry;
  adversarial challenge; agent eval suite with answer-stripped backtests and leak checks; summary
  grader; clean-OS matrix; merge-result re-check; post-release metric confirmation; incident
  linking and impact ranking; PPMA recall before interrupting a person; self-repair; attention
  metrics and dashboard; decisions D8–D11. See `docs/archive/reviews/review-4-factories.md`.
- **v4.4** — live builder path: `openjiuwen` Claude Code harness on the DeepSeek Anthropic endpoint,
  `Proposal.applied` for in-place worktree edits, policy after the turn with artifact filtering;
  live fixture run proved (104 563 tokens, $0.093938); PPMA memory reporting over the north
  contract (manifest, app token, deterministic `works.run_finished`); RG0 closed; T1.1/T1.5/T1.7/
  T1.10 delivered; ADRs 008–009.
- **v4.3** — M0 and M0.5 delivered: queue, replay, idempotent submit, claims, derived SQLite index,
  path policy, flow schema, ledger, evidence, fake harness, fixture repo, supervisor and all failure
  paths; CLI rewritten on argparse to meet the start budget; budgets measured and recorded.
  Mutation gate runs in Linux CI because mutmut has no native Windows support. RG0 was left open at
  that point; v4.4 closes it with the real adapter.
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
