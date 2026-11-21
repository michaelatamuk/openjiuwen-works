# ADR-009 — PPMA owns memory; Works reports finished runs

**Status:** accepted · 2026-11-21

## Context

The architecture gives each product one job: Works owns the loop, queue and proof; PPMA owns the
project's living memory. PPMA exposes a north contract: apps register a manifest, mint an app
token, and post events on one ingestion path (`POST /v0/spaces/{space}/messages`). Works already
has an append-only queue and ledger; replacing them would violate ADR-002 and blur ownership.

## Decision

- Works reports one `works.run_finished` event per finished run to PPMA.
- The `works` manifest is registered idempotently, an app token is minted with the owner token,
  and the event is posted with the app token. The owner/app tokens come from
  `WORKS_PPMA_TOKEN` / `PPMA_OWNER_TOKEN` and never from a file in the repository.
- The event id is a deterministic ULID derived from the run id, so a retry is deduplicated by
  PPMA instead of creating a second memory.
- The payload carries task, source, state, stop reason, verdict, tokens, USD, duration, base
  commit and the proof SHA-256; the evidence page is referenced as `works://`.
- Memory is a side effect: an unreachable PPMA is logged and never turns `proved` into `blocked`.
- Works does **not** read PPMA back yet. Recalling similar past failures and lessons is M4 work;
  the read routes (`/memory/views`, `/plans`, `/dispatches`) are already verified.

## Consequences

- Verified against `ppma serve --profile fake --auth dev`: manifest `200`, token `200`, event
  `202`, memory view version advanced.
- PPMA can be down while the factory keeps working; the ledger remains the local record.
- A strict PPMA needs a real owner token; the default `dev` only works with `--auth dev`.
- Two stores exist on purpose: the ledger is the factory's evidence, PPMA is the project's memory.

## Alternatives rejected

- **Write PPMA's SQLite directly**: couples two products to an internal schema.
- **Move the queue into PPMA**: makes memory the execution record and gives up the files/JSONL
  debugging path.
- **No memory**: the factory would relearn the same failures on every run.
