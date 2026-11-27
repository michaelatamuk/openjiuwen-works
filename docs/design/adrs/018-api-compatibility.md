# 018 - API compatibility is a checked promise

**Status:** accepted  
**Date:** 2026-11-25

## Context

The HTTP API is a real contract: the browser bundle, a native Windows client and a phone all speak it.
`docs/reference/generated/openapi.json` already gates drift (`dump_openapi.py --check`) and generates the
TypeScript client, but nothing stopped a refactor from silently removing an operation, a parameter or
a field that a client on the previous build still uses. "Be careful" is not a compatibility policy.

## Decision

1. The committed `docs/reference/generated/openapi.json` is the schema of the current build.
2. `docs/reference/generated/openapi.baseline.json` is the schema of the **last released** API. It only changes
   when a breaking change is deliberate and this ADR (or a successor) records it.
3. `scripts/check_api_compat.py` compares the two on every CI run and fails on:
   - a removed path or method;
   - a removed operation parameter;
   - a removed schema or property;
   - a changed property type;
   - a property that stops being required or newly becomes required.
4. Additive changes (a new endpoint, a new optional field) pass without touching the baseline.
5. `make api-compat` runs the same check locally; `--update` refreshes the baseline and must be part of
   the same pull request as the ADR amendment.

## Consequences

- Breaking a client is a CI failure, not a code-review opinion.
- The baseline is a file to maintain; refreshing it is a deliberate act, not a side effect of
  `dump_openapi.py --update`.
- The generated client keeps compiling because the schema is regenerated from the same source; the
  compatibility check protects the *previous* client, which is the part TypeScript cannot see.
- A genuinely breaking change needs either a second major version of the route (`/api/v2`) or a
  deprecation window where both shapes are served; this ADR does not grant permission to break it,
  only a place to record the decision.
