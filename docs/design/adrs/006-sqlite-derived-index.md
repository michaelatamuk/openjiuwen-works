# ADR-006 — A derived SQLite index for `status`

**Status:** accepted · 2026-11-21

## Context

ADR-002 says files and JSONL first, and SQLite only if the queue passes a few hundred tasks,
behind an interface. The engineering standard sets a load target: 10 000 tasks in the queue and
`status` under 100 ms.

Reading 10 000 projections from JSON cost 95 ms before any rendering, and a JSON index cost the
same. `orjson` crashed on this interpreter and would add a compiled dependency for a cache.

## Decision

- `events.jsonl` remains the only source of truth; `task.yaml` and `task.json` remain projections.
- `queue/index.sqlite3` is a derived cache with one row per task. It is written under the queue's
  index lock on every projection update, and can be rebuilt from `task.json` at any time.
- The read path (`works status`, `works/fast.py`) uses only the standard library and the index;
  it never imports pydantic or YAML.
- A missing or corrupt index is not fatal: `status` falls back to the projections, and
  `rebuild_index()` replaces the database.

## Consequences

- `status` is measured at 59 ms for 10 000 tasks (logic, best of five) on the development host.
- One more derived artifact to explain; the runbook documents how to rebuild it.
- The SQLite schema is not a persisted contract; only the JSONL events and their schemas are.

## Alternatives rejected

- **JSON index**: same read cost as the projections, no gain.
- **`orjson`/`msgspec`**: faster on paper; a compiled dependency and one crash already observed.
- **Daemon**: hides the cost instead of removing it, and adds lifecycle failures.
