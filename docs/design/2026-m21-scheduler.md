# M21 — queue and scheduler (design)

Status: planned. Nothing here is implemented yet; the checkboxes live in
`docs/design/2026-modern-plan.md`, and the actor rule is ADR 024.

## The problem

Today an incoming ticket creates a task in `queued` and stops. Starting work is a separate, explicit
act (`works run`, `works dispatch`, `POST /runs`). That is safe but incomplete: there is no sanctioned
way to say "run what is allowed, within limits, and stop where a person is needed". The only
alternatives were "start every ticket by hand" or "fire a run in the webhook handler", and the second
one is wrong:

- webhook deliveries repeat, so the same `ref` starts twice;
- a burst of twenty issues starts twenty models and burns the daily budget in a minute;
- one bad ticket blocks the repository and everything behind it;
- a run started while the person is using the UI makes the whole tool feel broken;
- ten plans queued for approval at once are not throughput, they are a backlog;
- there is no priority, no answer to "why is this task not running", and no kill switch.

Other factories solve this with an internal queue and a worker. We already have the queue, the claim
(`owner`), the journal and the budgets. What is missing is the **selection step** — policy, capacity
and the state of the machine — and a scheduler that explains every decision it makes.

## Model: arrival and execution are separate

```mermaid
flowchart TD
    A["Ticket / webhook / import"] --> Q["Queue<br/>dedupe by ref"]
    Q --> T{"Tick<br/>one dispatcher"}
    T -->|"disabled / paused"| W["Stays queued<br/>typed reason, since"]
    T --> P{"Policy<br/>source · label · product · repo · level"}
    P -->|"no"| W
    P -->|"yes"| AD{"Admission<br/>budget · slots · machine load<br/>attention · window · ETA"}
    AD -->|"no"| W
    AD -->|"yes"| C["Claim with lease<br/>heartbeat, TTL, reclaim"]
    C --> R["Run<br/>new run id, trigger=scheduler"]
    R --> L{"Autonomy level"}
    L -->|"L1"| G1["Stop at plan gate"]
    L -->|"L2"| G2["Stop at release gate"]
    L -->|"L3"| G3["Deliver only after<br/>a person approved"]
```

Four rules make this safe:

1. **A trigger only enqueues.** A webhook, an import or a label never starts a run. It writes a task
   and (optionally) a `scheduler.requested` event.
2. **One dispatcher decides.** Exactly one process holds the dispatcher lock and claims tasks; CLI and
   daemon share the same selection function, so there is no second policy path.
3. **Admission is explicit.** Policy says whether a task *may* run; admission says whether it *should
   run now*. Both are checked before the claim, and both produce a typed reason.
4. **The scheduler never decides a gate.** It may run *after* a person decided; it may never approve a
   plan or a release.

## Policy

One file, read on every tick: `~/.works/config/dispatch.yaml`. It is the only place that answers
"what may run". Defaults are off.

```yaml
enabled: false             # nothing is claimed until this is true
tick_seconds: 10

levels:
  default: L1              # L1 triage+plan, L2 to proof, L3 deliver after approval
  by_source:
    github: L1
    jira: L1
    detector: L2

allow:
  sources: [github, jira, detector]
  labels: ["works:auto"]   # empty = any label, but only for manual creation
  products: []             # empty = all configured
  repos: []                # empty = all configured
  risk_max_for_L2: medium
  risk_max_for_L3: medium

concurrency:
  global: 1                # runs in flight across the whole home
  per_repo: 1              # one worktree, one pinned base: never more

budget:
  daily_usd: 20            # overrides WORKS_DAILY_USD when set
  per_run_usd: 5           # pre-flight estimate cap
  on_exhausted: skip       # skip | pause

queue:
  max_age_hours: 72
  max_attempts: 2          # scheduler-driven attempts, excluding manual runs
  backoff_seconds: 300

resources:
  pause_when_job_pool_pct: 80
  pause_when_api_p95_ms: 300
  min_free_disk_gb: 5
  pause_on_provider_errors: 3   # within ten minutes

attention:
  max_waiting_plans: 3     # a person can only decide so many at once

windows:
  blackout: ["02:00-02:30"]     # backup/prune; no long run starts here

estimates:
  source: history          # history | plan | static
  min_samples: 5
  max_wall_clock_minutes: 90

priority: [risk, age]      # higher risk first, then oldest
paused: false
```

Validation is strict and typed: an unknown key, a level outside `L1..L3`, a negative limit, or
`risk_max_for_L3` above `medium` is a `config_error` at load, not a surprise at claim time. A missing
file means "disabled", not "run everything": the safe state is always the one that does nothing.

## Selection and admission

Selection is a pure function over (task, queue, policy, budget, locks, signals), so it is testable
without a run. The order matters: the cheapest checks first, the ones that need sampling last.

| stage | question | typical refusals |
|---|---|---|
| task | is this runnable at all? | `stale`, `duplicate`, `waiting_on_event`, `risk_too_high`, `attempts_exhausted`, `backoff` |
| policy | may it run here? | `disabled`, `paused`, `not_allowlisted`, `missing_label` |
| capacity | is there room? | `repo_busy`, `global_busy`, `budget_exhausted`, `run_budget_cap` |
| machine | is the host free? | `system_busy`, `interactive_load`, `low_disk`, `provider_degraded` |
| attention | can a person take it? | `attention_full` |
| window | does it fit the time? | `blackout`, `eta_unknown` |

Every refusal is recorded with a typed code, never a silent skip:

| code | meaning |
|---|---|
| `disabled` | `enabled: false` |
| `paused` | the kill switch is on |
| `not_allowlisted` | source/product/repo not allowed |
| `missing_label` | imported task without the required label |
| `budget_exhausted` | daily ceiling reached |
| `run_budget_cap` | the estimate is above `per_run_usd` |
| `repo_busy` / `global_busy` | a slot is taken |
| `stale` | older than `max_age_hours` |
| `waiting_on_event` | the task waits for a review/CI/deploy event |
| `attempts_exhausted` | the scheduler already tried `max_attempts` times |
| `backoff` | the retry delay has not elapsed yet |
| `risk_too_high` | the level or the policy forbids this risk |
| `duplicate` | merged into another task |
| `system_busy` | the daemon job pool is above the threshold |
| `interactive_load` | API p95 above the threshold; the person is using the UI |
| `low_disk` | free disk below the floor |
| `provider_degraded` | the model provider is failing right now |
| `attention_full` | too many plans already wait for a person |
| `blackout` | the next window is reserved for maintenance |
| `eta_unknown` | no history and no plan estimate, so the run cannot be sized |

Reasons are shown, not just stored: the waiting list in the GUI and `works scheduler status` answer
"why is this not moving" without reading logs.

## Autonomy levels

The level decides **where the run stops**, never who approves.

| level | runs | stops at | typical use |
|---|---|---|---|
| **L1** triage + plan (default) | reproduce, plan draft | `planning` — a person approves the plan | incoming tickets |
| **L2** to proof | L1 + build/check/proof | `proved` — a person approves the release | trusted repos, detectors |
| **L3** deliver after approval | everything, and delivery once a person has approved the release | never sets `released` by itself | low-risk, allowlisted |

L3 is deliberately not "full auto". A release approval is an **input** to L3, not a step it may skip.
The scheduler can act on a decision; it cannot make one. This is what keeps the two-gate model honest.

## Cost, slots and priority

- The daily ceiling is `WORKS_DAILY_USD`; the policy may override it, and `per_run_usd` is a pre-flight
  estimate. A task that cannot fit is refused, not started hopefully.
- `per_repo: 1` is not a preference: one worktree and one pinned base commit per repository, so two
  runs would race. The claim is the lock.
- Priority is `risk` first (high before medium before low), then age (oldest first). A manual run always
  outranks the scheduler: if a slot is free, the scheduler waits for the next tick.
- On `budget_exhausted` the queue keeps the tasks; with `on_exhausted: pause` the scheduler stops
  claiming until the operator resumes, and the reason is visible.

## Admission control: is the machine free?

A slot being free is not the same as the machine being free. Before a claim, the scheduler also asks
whether starting now would hurt the person using the tool or the run itself. The check is cheap and
runs on the same tick:

```mermaid
flowchart TD
    S["Candidate task"] --> B{"Fits the budget?<br/>daily USD · per-run estimate"}
    B -->|"no"| X1["budget_exhausted<br/>run_budget_cap"]
    B -->|"yes"| F{"Fits the slots?<br/>global · per repo"}
    F -->|"no"| X2["global_busy<br/>repo_busy"]
    F -->|"yes"| M{"Is the machine free?<br/>job pool · API p95<br/>disk · provider errors"}
    M -->|"no"| X3["system_busy · interactive_load<br/>low_disk · provider_degraded"]
    M -->|"yes"| H{"Can a person take it?<br/>plans already waiting"}
    H -->|"no"| X4["attention_full"]
    H -->|"yes"| W{"Does it fit the next window?<br/>ETA p90 · blackout"}
    W -->|"no / unknown"| X5["blackout<br/>eta_unknown"]
    W -->|"yes"| C["Claim with lease"]
    X1 --> Q["Back to the queue<br/>reason visible"]
    X2 --> Q
    X3 --> Q
    X4 --> Q
    X5 --> Q
    C --> R["Run"]
```

| signal | threshold | refusal |
|---|---|---|
| daemon job pool (the bounded pool from ADR 019) | occupied above `pause_when_job_pool_pct` | `system_busy` |
| API p95 over the last minute | above `pause_when_api_p95_ms` | `interactive_load` |
| free disk | below `min_free_disk_gb` | `low_disk` |
| provider failures in the last ten minutes | `pause_on_provider_errors` | `provider_degraded` |
| plans already waiting for a person | `max_waiting_plans` | `attention_full` |
| the next maintenance window | inside `blackout` and the estimate does not fit | `blackout` |

Signals are sampled, not guessed: the job pool and request timings already exist, disk is one
`statvfs` call, and provider errors are counted from run evidence. No new service, no agent on the
host.

The human is treated as a resource on purpose. A local factory is not limited by CPU — it is limited
by how many plan and release decisions one person can make well. Queueing ten plans for approval at
once is a backlog, not throughput, so `attention_full` keeps the queue honest.

### Duration is an estimate, never a promise

The scheduler does not need to know how long a fix takes; it needs to know whether the run **fits**
and what it may cost. Three sources, in order:

1. `history` — p50/p90 of `duration_ms`, `usd` and `tokens` for the same `repo × flow × risk`, with a
   minimum sample count (`min_samples`); the claim records how many samples backed the estimate;
2. `plan` — the planner's own size and risk estimate when history is thin;
3. `static` — a per-flow default.

With no source at all the answer is `eta_unknown`, not "probably fast". The estimate is used for three
decisions only: does it fit the daily budget (`run_budget_cap`), does it fit before a reserved window
(`blackout`), and what to show the person ("~40 min, $1.20, from 12 runs"). It is never shown as a
deadline.

Hard limits stay hard: `max_wall_clock_minutes` and `per_run_usd` stop a run that outgrows its
estimate. There is **no preemption** — a started run is not killed to make room for another; that
would throw away money and a worktree. The scheduler only decides what not to start.

## Triggers

- **Import**: `POST /sources` and `POST /tasks` accept `dispatch_on_import: true`. The flag is refused
  unless the policy allows the source, the label and the budget. It writes a `scheduler.requested`
  event — it never calls `run` directly.
- **Webhook**: the label rule is evaluated by the scheduler, not by the webhook handler. A label added
  or removed later changes eligibility on the next tick.
- **Manual**: the GUI "Run" button and `works run` bypass selection (a person is the trigger) but still
  take the repo lock, so a manual run and a scheduler claim cannot overlap.

## Idempotency and retries

- The claim is a lease in `queue/<task>/owner`, with kind `scheduler`, a heartbeat and a TTL. A second
  dispatcher exits with `conflict`; a dead holder is reclaimed after the TTL with a
  `scheduler.reclaimed` event.
- Retries are scheduler-driven and capped (`max_attempts`, default 2), with backoff. Only transient
  failures are retried (`harness_error`, a crashed builder, a network read); `policy_violation`,
  `conflict`, `tests_failed` and a failed verdict stop and stay visible.
- A new attempt is a **new run id** — that is intentional, not a duplicate. The task records
  `trigger: scheduler` and `attempt: n`, so the history explains itself.
- Webhook replays and imports stay idempotent: one task per `ref`, one delivery per marker, one
  attempt per lease.

## Visibility and control

- `GET /api/v1/scheduler` — enabled/paused, level map, last tick, counters per reason, the waiting list
  with reasons and `since`, budget used/remaining, current slots, the sampled signals and the estimate
  behind the next claim.
- `POST /api/v1/scheduler/pause`, `/resume`, `/tick` — the kill switch and a manual tick (used by
  tests).
- `works scheduler status|enable|disable|pause|resume|tick`; `works dispatch --watch` becomes the same
  loop with the same policy.
- Events: `scheduler.tick`, `scheduler.claimed`, `scheduler.skipped`, `scheduler.paused`,
  `scheduler.resumed`, `scheduler.reclaimed`, `scheduler.error`. The ledger records each claim with the
  reason it was chosen and the estimate it used.
- GUI: a Scheduler card (state, counters, waiting list, signals, budget, pause), `Run` on the task card,
  and `Dispatch ready (N)` in the queue header. Policy editing stays in the file — a YAML editor in the
  browser is not worth the risk.

## Invariants

1. With `enabled: false` (the default) the scheduler claims nothing.
2. The scheduler cannot approve a plan, a release, a deploy or a close: gate code refuses
   `actor_kind: scheduler`.
3. No automatic merge, deploy, rollback or issue close — ever, at any level.
4. No cross-repository parallelism beyond the configured slots; no second dispatcher.
5. Every claim, skip, pause and reclaim is an append-only event with a reason.
6. Policy, budget, capacity, machine state, attention and the window are checked **before** a run, not
   after. A started run is never preempted.
7. The policy file is the only source of truth for "what may run"; environment variables only set
   limits.
8. A missing or invalid policy means "do nothing", never "do everything".

## Non-goals

- a cloud queue, a hosted scheduler or a remote worker;
- a cron expression language (a tick interval is enough locally);
- multi-tenant priorities or per-user quotas;
- auto-approval of either gate, auto-merge, auto-deploy, auto-close;
- running two tasks in one repository at once;
- preemption of a started run, or CPU-level scheduling.

## Acceptance

| proof | expected |
|---|---|
| policy off | no claim, reason `disabled` |
| L1 with a labelled ticket | reaches `planning` within two ticks, then waits for a person |
| unlabelled import | stays `queued`, reason `missing_label` |
| two dispatchers | exactly one claim; the second gets `conflict` |
| crash mid-run | lease reclaimed after TTL; one new attempt; no duplicate branch or comment |
| budget exhausted | no claims, reason `budget_exhausted`, tasks still queued |
| pause | no claims; resume restores claims |
| L2 | stops at `proved` |
| L3 after a person approves | delivers; without the approval it does not |
| scheduler calls `approve-plan`/`release` | typed refusal |
| retry | transient failure retried up to the cap; `tests_failed` is not retried |
| job pool saturated | no claim, reason `system_busy` |
| UI under load | no claim, reason `interactive_load` |
| three plans already waiting | no fourth claim, reason `attention_full` |
| empty history and no plan estimate | reason `eta_unknown`, never a blind start |
| long estimate before a blackout window | not started; it waits for the window to pass |
| started run over `max_wall_clock_minutes` | stopped by the cap, evidence says why; no other run is preempted |
| invalid policy | `config_error` at load; nothing is claimed |

## Open questions

Decided at implementation, with the answer written back into this page:

1. Sample window for history: last N runs per repo, or last 30 days? (Leaning: last 20 runs, at most 90
   days old.)
2. Does `max_waiting_plans` count release gates too, or only plans? (Leaning: one counter for both,
   since both consume the same attention.)
3. Is `blackout` allowed to start a short L1 run? (Leaning: yes, if the p90 estimate fits inside it;
   L2/L3 never.)
4. Should a detector default to L2 while a tracker ticket defaults to L1? (Current default says yes.)
5. Where does the dispatcher lock live: `state/dispatcher.lock` next to the queue, or OS-level
   (named mutex on Windows, file lock elsewhere)? (Leaning: file lock, portable and visible.)

## Work breakdown

| # | Work | Days |
|---|---|---|
| M21.1 | policy loader, strict validation, defaults off | 2 |
| M21.2 | pure selection function: task, policy and typed reasons | 2 |
| M21.3 | claim lease, dispatcher lock, stale reclaim | 2 |
| M21.4 | scheduler loop in the daemon + `dispatch --watch` sharing it | 2 |
| M21.5 | levels L1/L2/L3 mapped to stop states; `scheduler` actor | 2 |
| M21.6 | admission control: budget, slots, priority, job pool, API load, disk, provider, attention, blackout, ETA | 4 |
| M21.7 | `dispatch_on_import` and label-gated triggers | 1 |
| M21.8 | bounded retries and attempt bookkeeping | 2 |
| M21.9 | `GET /scheduler`, counters, waiting reasons, signals, events | 2 |
| M21.10 | pause/resume and the kill switch | 1 |
| M21.11 | GUI: Scheduler card, Run, Dispatch ready | 3 |
| M21.12 | docs, ADR 024, acceptance tests | 2 |

**~25 engineer-days**, or **~30 with contingency**.
