# ADR-014 — One proof, two readings

**Status:** accepted · 2026-11-21

## Context

The first read-only preview answered technical questions well: run metadata, verdict, risk,
decision, commands, diff, policy, cost and timeline. A reporter or product owner could not answer
the first question — *was my problem fixed?* — without reading the factory's language (`proved`,
`P0`, `checks_sha`, `evidence_sufficient`).

Competitor systems converge on a different default. Warp opens on an Inbox of items **waiting on
you**; Factory presents Mission Control with a summary, workers and validators; Devin groups sessions
as **Working / Ready / Blocked / Inactive** and offers Session Insights; the GitHub Copilot app puts
diff, terminal and browser side by side and keeps the plan approval before implementation.

A separate "simple" GUI would drift from the evidence and double the maintenance. Hiding the proof
would remove the audit trail that makes the factory trustworthy.

## Decision

- Keep **one proof** as the source of truth and render it in **two layers**:
  - **Summary** (default): fixed/needs attention, what changed for the user, what was checked, what
    was not, who decided, where it goes next, what to do.
  - **Evidence** (one click): run metadata, verdict, risk, decision, commands, diff, policy, cost and
    timeline.
- The Summary is derived from the same evidence; it never hides a contradiction. Every technical
  detail is one tab away.
- Use human labels in the Summary (`Fixed and verified`, `Needs attention`, `Waiting for a person`,
  `Checks passed`, `Low risk`, `Proceed`) and keep raw states and reason codes in Evidence.
- Group the queue as **Needs you / Working / Ready / Done**, not by internal state name.
- Deep links carry the view: `#/task/<id>` and `#/task/<id>/evidence`.
- The UI is read-only. It never becomes a chat surface and Mira never replaces status text.
- The preview is vanilla HTML/CSS/JS; the final window is the React 19 + TypeScript + Vite stack in
  plan §6.5 with Playwright and axe.

## Consequences

- A reporter, support and product can answer the first question without learning the factory
  vocabulary; an engineer keeps the full audit trail one click away.
- The Summary needs a human-readable impact sentence. Until the builder produces one, it is derived
  from the issue title and verdict; that is honest but generic.
- The two layers can drift if the Summary is hand-written. It must be computed from evidence, never
  authored separately.
- The "Needs you" group is the default attention surface; the flat queue remains for operators.
- The read-only API stays GET-only; write actions and gate interactions are a later window.

## Alternatives rejected

- **A separate non-technical app**: two products, two sources of truth and guaranteed drift.
- **Only a technical console**: accurate, but useless to the person who reported the problem.
- **Only a friendly summary**: hides the evidence and turns trust into a green badge.
- **Chat-first UI**: a conversation is not a proof and makes status hard to scan.
- **A dashboard of activity**: counts and charts do not answer "was my problem fixed?".
