# Gates (stage 4 and stage 8)

> **Doc status:** active · **Owner:** Michael · **Last reviewed:** 2026-11-27

A gate is a recorded human decision bound to an artefact, not a chat reply. The plan gate and the
release gate share identity, quorum, expiry and audit mechanics; the release gate adds the packet,
the blockers and the risk roles.

## The plan gate

`POST /api/v1/actions {"action": "approve-plan", "task_id": …, "decision": …}`

| decision | effect | requires |
|---|---|---|
| `approved` | task moves to `plan_approved` | a named person |
| `changes_requested` | task stays in `planning`; the next plan version needs a new decision | a comment |
| `rejected` | task moves to `blocked` | a reason |

`GET /inbox` returns `gates`: planning tasks with a drafted plan, `waiting_hours` and `overdue`
(`WORKS_GATE_REMINDER_HOURS`, default 24).

## The release gate

The release packet is read-only; the gate is the human decision that follows it.

### The packet

`release_packet(paths, task_id)` returns commit, run id, proof fingerprint, plan and release gates,
risk with its reasons, file and line counts, a plain-language summary, owners, residual `not_tested`,
verdict and challenge outcomes, tokens/USD, plan estimate, `proof_verified`, `delivery_configured`,
rollback and **typed blockers**.

A blocker is never a warning: `not_proved`, `plan_gate_missing`, `release_gate_missing`, `proof_unbound`,
`proof_mismatch`, `must_pass_failed`, `challenge_blocked`, `policy_violation`, `stale_plan`,
`stale_release`, `expired_release`, `no_run`, `unreadable_proof`.

The proof is re-verified when the packet is built (`works proof verify`), so an edited page or artifact
blocks the release.

### Decisions

`POST /api/v1/actions {"action": "release", "task_id": …, "decision": …}`

| decision | effect | requires |
|---|---|---|
| `approved` | task becomes `released` | a ready packet, a named person, owner approval for high risk |
| `changes_requested` | stays `proved` | a comment |
| `rejected` | task becomes `blocked` | a reason |

## Who can decide

- `actor_kind` must be `person`; `agent`, `harness`, `model`, `builder`, `mira` and `ai` are refused
  server-side.
- Identity is a name plus a device label, both stored in the event.
- `WORKS_REQUIRE_QUORUM=1` makes two distinct person/device pairs necessary; the same pair twice is
  refused. Default off for a single-user install.
- `WORKS_REQUIRE_OWNER_APPROVAL=1` requires the release approver to be one of the risk owners for
  high or critical risk.

## Expiry and staleness

- A plan approval carries `expires_at` (default 168 hours, `WORKS_APPROVAL_TTL_HOURS`). The builder
  checks the latest approved event: an expired approval, or one whose plan hash no longer matches,
  stops the run with `needs_plan_approval` and asks for a new decision.
- A release approval carries `expires_at` (default 72 hours, `WORKS_RELEASE_TTL_HOURS`); an expired
  approval is a blocker (`expired_release`) and delivery refuses until a new decision.
- Moving the base commit or changing the checks invalidates the plan approval through the plan hash.
  Any new proof or commit makes the release approval stale.

## Audit

`gate.decided` is append-only. A plan decision contains gate, decision, by, device, actor_kind,
comment, plan id, plan hash, plan version, commit, checks hash, expires_at and the quorum flag. A
release decision adds commit, proof hash, run id, packet hash, released_at, expires_at and the quorum
flag; the same record is written to `release.json` in the run directory.

## Reopened tasks

A reporter reply moves a released task back to `queued` (see [reporter.md](../capabilities/reporter.md)).
The old approvals do not carry over: the plan gate is bound to the plan hash and the release gate to
the commit and the proof fingerprint, so a stale decision is refused rather than reused. A reopened
task pays for a fresh plan draft and a fresh run.
