# Gates (stage 4 and stage 8)

> **Doc status:** active · **Owner:** Michael · **Last reviewed:** 2026-11-27

A gate is a recorded human decision bound to an artefact, not a chat reply. This page covers the shared
mechanics; the release-specific packet and blockers are on `release-gate.md`.

## Decisions

`POST /api/v1/actions {"action": "approve-plan", "task_id": …, "decision": …}`

| decision | effect | requires |
|---|---|---|
| `approved` | task moves to `plan_approved` | a named person |
| `changes_requested` | task stays in `planning`; the next plan version needs a new decision | a comment |
| `rejected` | task moves to `blocked` | a reason |

`GET /inbox` returns `gates`: planning tasks with a drafted plan, `waiting_hours` and `overdue`
(`WORKS_GATE_REMINDER_HOURS`, default 24).

## Who can decide

- `actor_kind` must be `person`; `agent`, `harness`, `model`, `builder`, `mira` and `ai` are refused
  server-side.
- Identity is a name plus a device label, both stored in the event.
- `WORKS_REQUIRE_QUORUM=1` makes two distinct person/device pairs necessary; the same pair twice is
  refused. Default off for a single-user install.

## Expiry and staleness

An approval carries `expires_at` (default 168 hours, `WORKS_APPROVAL_TTL_HOURS`). The builder checks
the latest approved event: an expired approval, or one whose plan hash no longer matches, stops the
run with `needs_plan_approval` and asks for a new decision. Moving the base commit or changing the
checks has the same effect through the plan hash.

## Audit

`gate.decided` is append-only and contains: gate, decision, by, device, actor_kind, comment, plan id,
plan hash, plan version, commit, checks hash, expires_at and the quorum flag. The CLI and the UI write
the same shape.


## Reopened tasks

A reporter reply moves a released task back to `queued` (see `reporter.md`). The old approvals do
not carry over: the plan gate is bound to the plan hash and the release gate to the commit and the
proof fingerprint, so a stale decision is refused rather than reused. A reopened task pays for a
fresh plan draft and a fresh run.
