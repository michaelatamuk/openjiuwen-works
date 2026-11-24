# 016 - One local daemon, many clients

**Status:** accepted (Phase 7 cutover)

## Context

Works started as a CLI plus a read-only stdlib preview. The migration moved every surface onto a
FastAPI application: the web UI, long-running jobs, live SSE updates, task creation, release and
delivery. The same machine may also host a native Windows app or serve a phone on the LAN, and the
CLI should keep its one-shot behaviour.

## Decision

- `works daemon` owns one Works home. A writable daemon takes `.works/state/daemon.lock`; a second
  writable daemon for the same home refuses to start. Reads may be served read-only without the lock.
- `/api/v1` is the only HTTP contract. Reads are open on loopback; writes need the persistent bearer
  token or a session cookie created from the bootstrap URL. Host and Origin are checked.
- Long actions are jobs: `POST` returns `202` plus a job id; `GET /jobs/{id}` is the status. The UI
  waits for the terminal state and refreshes; a daemon restart fails orphan jobs and releases their
  queue owner.
- Live updates are named SSE events with an id, a replay ring and a `resync` marker. `ask` is a
  separate streamed endpoint.
- `works ui` is the same application plus the built SPA. It is a distribution convenience, not a
  separate backend; native clients use the API directly.
- Default flows and worker scripts ship inside the wheel under `works/resources`; a fresh home gets
  its `flows/` copied from there. The CLI, daemon and workers all use the same package.
- The detached daemon records the pid it reports after Uvicorn starts (the Windows venv
  `python.exe` is a launcher), so `daemon stop` never targets the launcher or an unrelated reused
  pid.

## Consequences

- Multiple clients share one queue, ledger and run history; per-task locks and idempotency keys
  prevent duplicate work.
- Remote access is deliberately not enabled by default. A host that needs it must add trusted hosts,
  authenticate reads, and use a tunnel or TLS; loopback remains the safe default.
- Development without the `server` extra still works for the CLI; `works ui`/`daemon` fail with an
  install hint.
- Rollback to the pre-FastAPI cutover is the `pre-fastapi` tag.
