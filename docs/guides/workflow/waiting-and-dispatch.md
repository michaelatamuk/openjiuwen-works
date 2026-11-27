# Waiting and dispatch

A factory does not finish a task just because an agent stopped. It waits.

## States

```
proved ──► waiting_review ──► releasing ──► waiting_ci ──► waiting_deploy ──► released
   │              │                 │              │                │
   └──────────────┴─────────────────┴──────────────┴────────────────┴──► blocked
```

Every wait records **what it waits for**, **which event wakes it**, a **deadline**, the **next
state** and the **default** if the deadline passes. While waiting, the task is not terminal and no
agent is running.

## Put a task to wait

```bash
works wait <task> --on review --wake-on review_approved
works wait <task> --on ci --wake-on ci_passed --deadline 2026-11-21T18:00:00+00:00
works wait <task> --on deploy --wake-on deployed --next released
```

| `--on` | State | Default next |
|---|---|---|
| `review` | `waiting_review` | `releasing` |
| `ci` | `waiting_ci` | `waiting_deploy` |
| `deploy` | `waiting_deploy` | `released` |

The default on an expired deadline is `blocked`; pass `--default` to override. A task can only enter
a wait the state machine allows (for example, `ci` starts from `releasing`, not from `proved`).

## Wake it

```bash
works wake <task> --event review_approved
```

A wake with the wrong event is refused. The event, the wait reason, the transition and the time are
all in `events.jsonl`, so the wait is auditable and replayable.

## Dispatch

```bash
works dispatch --limit 10 --approve-plan \
  --scenarios fixtures/scenarios/fix-add.yaml \
  --trace fixtures/traces/fix-add.json
```

`dispatch` claims queued tasks (the claim is `O_EXCL`; two dispatchers cannot own one task), runs
them one at a time, releases the claim and prints the runs. `--watch` keeps the loop alive and sleeps
`--interval` seconds when no task is ready. A kill between tasks is safe: only claimed work is
in-flight, and a completed task is no longer queued.

The dispatcher is not the supervisor. The supervisor advances one task; the dispatcher decides which
task is ready. That separation is what lets a future GUI, cron or webhook call the same primitive.

## What is not here yet

- Waking from a real GitHub review, CI or deployment webhook. For now the event is a CLI command;
  the subscription is recorded in the task.
- Automatic expiry in the dispatcher. `Queue.expire_wait` exists and is tested; the dispatcher will
  call it on each pass when the forge/CI ports land.
- A GUI for the waiting lanes. The read-only preview after M1 shows the state and the wake event.
