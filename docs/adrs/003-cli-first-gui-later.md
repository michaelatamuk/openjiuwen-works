# ADR-003 — CLI is the first window

**Status:** accepted · 2026-11-21

## Context

The product promises a "window" where a person reports, watches and approves. A polished GUI is
expensive and, before the loop works, it would polish the wrong thing.

## Decision

v0 ships a CLI: `submit`, `run`, `status`, `approve`, `trace`, `doctor`, all with `--json`. A web
window is a separate `web/` app, built only after M2, against the standard in the plan (§6.5):
React 19, Tailwind v4, shadcn/ui, SSE, keyboard-first, WCAG 2.2 AA.

## Consequences

- The loop is validated without UI risk.
- Every CLI command is also an API for the future UI; `--json` is the contract.
- The first users are comfortable in a terminal; that is acceptable for v0.

## Alternatives rejected

- **GUI first**: attractive, slow, and it would hide a weak verifier behind good design.
- **TUI**: better than plain text, still not the product.
