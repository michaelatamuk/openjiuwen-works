# ADR 022 — Gate decisions, identity and expiry

Status: accepted, 2026-11-25.

## Context

A plan gate that only records `by: "ui"` cannot answer who decided, whether an agent decided, or
whether the approval still applies. The product has no accounts, so identity has to come from what a
local product actually has: a person's name plus the device they used.

## Decision

1. **Identity is `by` + `device`**, both recorded in the append-only `gate.decided` event. The CLI
   passes a name (default OS user); the API passes the name the UI supplies and a device label.
2. **Agents cannot decide.** `actor_kind` must be `person`, and names in {agent, harness, model,
   builder, mira, ai} are refused server-side. A harness has no path to a gate.
3. **Three outcomes.** `approved` moves to `plan_approved`; `changes_requested` needs a comment and
   keeps the task in `planning`; `rejected` needs a reason and moves to `blocked`.
4. **Approval expires.** A decision carries `expires_at` (default 168 hours,
   `WORKS_APPROVAL_TTL_HOURS`); the builder refuses an expired or hash-mismatched approval and asks
   for a new gate decision.
5. **Quorum is opt-in** (`WORKS_REQUIRE_QUORUM=1`). When enabled, the first approval records
   `gate.approval` and the task stays in planning; a second, different person/device completes it.
   The same person on the same device cannot satisfy the quorum. Default off: one named person is
   enough for a local single-user install, and self-approval by an agent is already impossible.
6. **Notifications are derived.** `GET /inbox` lists planning tasks with a drafted plan, their
   waiting time and an `overdue` flag (`WORKS_GATE_REMINDER_HOURS`, default 24). No background timer
   is invented; the operator sees the age whenever they look.

## Consequences

- The gate event is a complete audit record; nothing is edited after the fact.
- A multi-user install can turn quorum on; a single-user install is not blocked by a second seat.
- High-risk paths currently rely on the risk owners being named in the flow; a per-path quorum is a
  later refinement, not a hidden default.
