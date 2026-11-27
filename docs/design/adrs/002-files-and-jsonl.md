# ADR-002 — Files and JSONL before a database

**Status:** accepted · 2026-11-21

## Context

The queue holds work items; each run produces events, a verdict, evidence and a ledger row. v0
handles tens of tasks, not thousands. A database server adds operations we do not need yet.

## Decision

- Append-only `events.jsonl` per task is the source of truth.
- `task.yaml` is a projection, derived by replay.
- A single `ledger.jsonl` for finished runs.
- SQLite (stdlib) only if the queue passes a few hundred tasks, behind a repository interface.

## Consequences

- Debugging is `cat`, `grep` and `jq`; no server to run.
- Replay is trivial, which makes the state machine testable.
- Concurrency limited to file locking; acceptable for one operator on one machine.
- Migration to SQLite is a repository swap, not a rewrite.

## Alternatives rejected

- **Postgres + queue**: correct at scale, heavy at zero.
- **Redis/Celery**: a broker for a single-process supervisor.
