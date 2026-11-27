# Architecture overview

> **Doc status:** active · **Owner:** Michael · **Last reviewed:** 2026-11-27

Works is a software factory: one signal goes in, a released fix comes out, and the fix lands back
where the bug was seen. People appear at exactly two gates — the plan and the release. This page is
the stable design; delivery status is in [the roadmap status](../roadmap/status.md), and the bar for
a change is in [the engineering standard](../guides/contributing/engineering-standard.md).

## The promise

A filed issue becomes a merged change with a one-page proof, and the reporter is told. "Released"
means merged and confirmed; deploy is out of scope.

## What it is not

- No chat surface and no general-purpose coding assistant.
- No deploy, canary or rollback automation. Release = merged PR + confirmation.
- No multi-tenant, SSO or billing; one operator, one home, one writable daemon.
- No arbitrary repositories in v0: the factory first fixes its own code. External products are v1.
- No automatic merge to a protected branch.

## Shape

```
 signal ─► supervisor ─► reproduce ─► plan ║gate 1║ ─► build ─► check ─► proof ─► release ║gate 2║ ─► return
                │                                                                              │
                └──────────────────────── events.jsonl ──► ledger ◄───────────────────────────┘
```

**Supervisor:** one resumable process (`works run`) that advances state until a gate or a terminal
state. Heartbeat every 10 s; on restart it resumes from the last event. The operator does not click
through nine commands.

## Invariants

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
11. **Checks outlive changes.** Policy, flows, scenarios, review rules and risk rules are read from
    the trusted base, never from the worktree. A change cannot edit the check that judges it;
    changing a check is a separate task with its own proof.
12. **A verdict is bound to the exact commit.** A new commit invalidates the verifier result,
    challenger verdict and approval; the gate re-checks at the commit being merged.
13. **Every new gate starts in observe mode.** It logs what it would block until its false positives
    are reviewed; only then can it enforce.
14. **No blocking prompt in the engine path.** A question to a person becomes a wait with a wake
    event, a deadline and a default.
15. **External actions are idempotent and safe to repeat.** A retry never duplicates a merge, a
    comment, a release or a task.

## Components

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

## Flows are node graphs

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

## Data

- **Events** — `queue/<id>/events.jsonl`, append-only, the only writer is the supervisor.
- **Task projection** — derived; never edited by hand.
- **Run** — `runs/<id>/run.json`: prompt hash, model id + version, provider, attempts, cost, duration.
- **Verdict** — `runs/<id>/verdict.json`: per-scenario, weights, blocking failures.
- **Evidence** — `runs/<id>/evidence.md` (rendered) + `evidence.json` (computed).
- **Ledger** — `ledger.jsonl`; plus `ledger/escapes.jsonl` for post-release attribution.
- **Idempotency** — `(source.kind, source.ref)`; a duplicate webhook returns the existing task.

## One run

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

## Where the contracts live

- Lifecycle: [signal](../reference/lifecycle/signal-intake.md) →
  [reproduce](../reference/lifecycle/reproduce.md) → [plan](../reference/lifecycle/planning.md) →
  [build](../reference/lifecycle/build.md) → [check](../reference/lifecycle/check.md) →
  [proof](../reference/lifecycle/proof.md) → [gates](../reference/lifecycle/gates.md) →
  [deliver](../reference/lifecycle/deliver.md) → [confirm](../reference/lifecycle/confirm.md).
- [Planner](planner.md) — the planning contract and its delivery phases.
- [HTTP API](../reference/platform/http-api.md) and [scheduler](../reference/platform/scheduler.md).
- [Architecture decisions](../adrs/README.md) — one record per expensive choice.
