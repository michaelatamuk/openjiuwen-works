# Release gate (stage 8)

The release packet is read-only; the gate is the human decision that follows it. Identity, TTL and
quorum mechanics are shared with the plan gate (`gates.md`); this page adds what is release-specific.

## The packet

`release_packet(paths, task_id)` returns commit, run id, proof fingerprint, plan and release gates,
risk with its reasons, file and line counts, owners, residual `not_tested`, verdict and challenge
outcomes, tokens/USD, plan estimate, `proof_verified`, `delivery_configured`, rollback and **typed
blockers**.

A blocker is never a warning: `not_proved`, `plan_gate_missing`, `release_gate_missing`, `proof_unbound`,
`proof_mismatch`, `must_pass_failed`, `challenge_blocked`, `policy_violation`, `stale_plan`,
`stale_release`, `expired_release`, `no_run`, `unreadable_proof`.

The proof is re-verified when the packet is built (`works proof verify`), so an edited page or artifact
blocks the release.

## Decisions

`POST /api/v1/actions {"action": "release", "task_id": …, "decision": …}`

| decision | effect | requires |
|---|---|---|
| `approved` | task becomes `released` | a ready packet, a named person, owner approval for high risk |
| `changes_requested` | stays `proved` | a comment |
| `rejected` | task becomes `blocked` | a reason |

## Identity and roles

- `actor_kind` must be `person`; agent/harness/model/builder names are refused.
- The event records the name and device.
- `WORKS_REQUIRE_OWNER_APPROVAL=1` requires the approver to be one of the risk owners for high/critical
  risk.
- `WORKS_REQUIRE_QUORUM=1` needs two distinct person/device pairs; the first approval is recorded as
  pending.

## Expiry

`WORKS_RELEASE_TTL_HOURS` (default 72) sets the approval expiry; an expired approval is a blocker
(`expired_release`) and delivery refuses until a new decision. Any new proof or commit also makes the
approval stale.

## Audit

`gate.decided` for a release carries decision, by, device, actor kind, comment, commit, proof hash, run
id, packet hash, released_at, expires_at and whether a quorum was required. The same record is written
to `release.json` in the run directory.
