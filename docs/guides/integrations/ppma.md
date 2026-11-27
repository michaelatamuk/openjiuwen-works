# PPMA memory

Works reports every finished run to PPMA. PPMA is the project's living memory; Works keeps the
queue, ledger and proof.

## Start PPMA locally

Use the fake profile for development; it does not touch your real PPMA data:

```bash
cd C:\Workspace\openjiuwenothers\PPMA
.venv\Scripts\ppma.exe serve --profile fake --auth dev --port 8766 --agent fake
```

`--auth dev` accepts any bearer token as the owner; `strict` needs `PPMA_OWNER_TOKEN`.

## Report a run

```bash
works run <task> --ppma http://127.0.0.1:8766 --live --approve-plan --scenarios ...
```

or set `WORKS_PPMA_URL=http://127.0.0.1:8766`. The reporter:

1. `PUT /v0/apps/works/manifest` — the `works.run_finished` event and its payload schema;
2. `POST /v0/apps/works/token` — an app token, minted with the owner token;
3. `POST /v0/spaces/me/messages` — one event with a deterministic ULID derived from the run id.

Tokens come from `WORKS_PPMA_TOKEN` or `PPMA_OWNER_TOKEN`; `dev` is the local default. A failed
memory write is logged and never changes the run's verdict.

## Event

```json
{
  "type": "works.run_finished",
  "payload": {
    "task_id": "t-…",
    "run_id": "r-…",
    "source": "manual:LIVE-2",
    "state": "proved",
    "stop_reason": "completed",
    "verdict": "allow",
    "tokens": 104563,
    "usd": 0.093938,
    "duration_ms": 115602,
    "base_commit": "…",
    "proof_sha256": "74a2f1…"
  },
  "resources": [{ "uri": "works://runs/r-…/evidence", "mime_type": "text/markdown" }]
}
```

Verified against the fake PPMA: manifest `200`, token `200`, event `202`, memory view version
advanced.

## Backfill already-finished runs

A run created before PPMA was configured is not lost: `run.json` and `evidence.json` are enough.

```powershell
works --home C:\path\to\workspace memory backfill --ppma http://127.0.0.1:8766 --dry-run
works --home C:\path\to\workspace memory backfill --ppma http://127.0.0.1:8766
```

- scans `runs/*/run.json` newest first, pairs each run with its task projection and evidence;
- sends the same `works.run_finished` event the live path sends, so the deterministic ULID makes a
  second backfill a duplicate rather than a second memory;
- a run without `evidence.json` is skipped and a broken run is reported without hiding the rest;
- `--dry-run` lists what would be sent and calls no PPMA; `--json` returns per-run status.

Verified on 2026-11-21 against `ppma serve --profile fake --auth dev`: three demo runs were accepted
on `POST /v0/spaces/me/messages`.

## Read side

The read side (`/v0/spaces/me/memory/views`, `/plans`, `/dispatches`) is available for the memory
loop. `works memory recall --ppma URL --view about_me` reads memory statements for an operator;
automatic recall before interrupting a person is T2.21.

## Failure behaviour

- PPMA down: a warning in the structured log, run continues.
- Token rotated: the reporter mints a new token and retries the same event id once.
- Duplicate delivery: PPMA returns `duplicates`; the event id makes that a success.
