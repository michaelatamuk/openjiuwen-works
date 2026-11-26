# ADR 024 — The scheduler is a system actor that runs, never decides

Status: accepted, 2026-11-26 (M21.5 landed with tests).

## Context

Adding a scheduler that picks queued tasks raises two temptations:

1. let the trigger start a run directly (webhook → run), and
2. let "full autonomy" also approve the plan and the release, so the pipeline never stops.

Both break the property the product is built on: a named person on a device owns the two gates, and a
webhook or a label is not a person. A trigger is untrusted input; a label can be added by anyone with
write access to the tracker, and a webhook delivery can be replayed.

At the same time, "start every ticket by hand" is not a product either. The queue already exists, and
a selection step with budgets and locks is the missing piece.

## Decision

1. **Arrival and execution are separate.** A trigger only enqueues (and may emit
   `scheduler.requested`). A single dispatcher claims tasks from the queue by policy.
2. **The scheduler is a new actor kind: `scheduler`.** It may claim and start runs. It may **not**
   approve a plan, a release, a deploy or a close; `check_actor` refuses it with the same typed error
   as an agent identity. The run records `trigger: scheduler`, the task records the attempt number.
3. **Autonomy means "where the run stops", not "who approves".** L1 stops at the plan gate, L2 at the
   release gate, L3 delivers **after a person has approved the release**. No level can set `released`
   by itself.
4. **Policy is one file, default off.** `~/.works/config/dispatch.yaml` is the only source of truth
   for what may run; it is loaded and validated on every tick, and an invalid file is a `config_error`
   rather than a partial apply.
5. **Every decision to run or not run is an event with a reason** (`scheduler.claimed`,
   `scheduler.skipped` with a code, `scheduler.reclaimed`). A scheduler that cannot explain itself is
   indistinguishable from a bug.
6. **One dispatcher per home.** A lock file with a heartbeat; a second process exits with `conflict`.
   Claims are leases with a TTL, so a crashed dispatcher does not wedge the queue.
7. **Retries are bounded and typed.** `max_attempts` (default 2) applies only to transient failures;
   a failing check or a policy violation stops and stays visible, as in ADR 023.
8. **No automatic merge, deploy, rollback or issue close**, at any level. Those stay human decisions
   next to the gates.

## Consequences

- The default install behaves exactly as today: nothing runs until `enabled: true` and a labelled,
  allowlisted task exists.
- "Add a ticket and it starts" becomes true for allowlisted sources, but it starts into **triage and
  planning**, not into a release. The human cost per ticket is one plan decision, not one command.
- Budget and concurrency are enforced before a run, together with the machine's own state (job pool,
  API load, disk, provider health, waiting plans, maintenance windows) and a duration estimate, so a
  burst of tickets produces a visible queue and a reason, not twenty parallel builds.
- A scheduler bug can waste budget and produce bad plans; it cannot ship code. The blast radius is
  bounded by design.
- Tests must cover the refusal path: `scheduler` calling either gate is a typed error.

## Alternatives rejected

- **Run in the webhook handler.** No dedupe window, no budget, no lock, no visibility; replays run
  twice.
- **Cron only.** A time trigger without eligibility is the same problem with extra delay; the policy
  is the hard part.
- **Full auto (approve both gates).** Removes the only human moment that makes the proof meaningful
  and contradicts ADR 022.
- **Per-repository parallelism with separate worktrees.** More moving parts than a local-first tool
  needs, and it multiplies the cost of a mistaken ticket. Revisited in ADR 027 once worktrees and the
  job pool were already in place.
- **A hosted scheduler.** Contradicts the local-first, one-daemon-owns-one-home model (ADR 016).
