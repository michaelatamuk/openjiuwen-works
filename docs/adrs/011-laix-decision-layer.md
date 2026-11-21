# ADR-011 — LAIX is the optional decision layer, not the factory

**Status:** accepted · 2026-11-21

## Context

The plan and release gates are deterministic rules (`action: ask`, path exceptions, the verifier's
verdict). They are correct but opaque: a rule cannot say why it fired, how confident it is, what it
would have done instead, or what the decision costs in human attention. The attention inbox has the
same gap — waiting tasks are listed, not ranked by risk, deadline and interrupt cost.

LAIX (`0.18.0`, dependency-free, Apache-2.0) is our own decision layer. It takes a `DecisionRequest`
(situation, options, evidence, constraints) and returns a `Decision`: one of `wait`, `observe`,
`guide`, `ask`, `act`, `verify`, `escalate`, with a reason code, confidence, score, approval flag,
alternatives and a trace id. It also provides `AttentionScheduler` and `CommitmentGraph`. It is
explicitly not an agent framework, workflow engine, model or verifier.

## Decision

- Works exposes one **`DecisionPort`** with two adapters: `DeterministicGate` (default, no
  dependency) and `LaixGate` (extra `works[decision]`, pinned `laix==0.18.0`).
- LAIX may decide **only** the plan gate, the release gate and attention ordering. It never opens a
  gate, admits a denied path, skips a deterministic node, replaces the verifier or writes state.
- **Path deny runs before the decision; the verifier's verdict runs after it.** Either can veto the
  outcome; neither is negotiable by the decision layer.
- Decisions are built from recorded evidence only: reproduction result, plan spec and scenario ids,
  verifier verdict, policy result, diff and touched paths, budget left, deadline, open commitments.
  Agent-supplied urgency or free-form prose is never an input.
- Rollout is `off → shadow → per-gate opt-in`. Shadow records differences without changing a
  transition. Opt-in requires the T2.14 replay showing no case where LAIX allows what policy or the
  verifier refuses.
- A missing, invalid, low-confidence or timed-out decision **falls back to the deterministic gate**.
  The system fails closed.
- `Decision.to_dict()` is stored whole as a `decision.made` event and as the proof's Decision
  section; code branches on `reason_code`, never on `rationale`.
- `AttentionScheduler` ranks waiting tasks and gate requests under an explicit
  `human_attention_budget`; deferred items keep a deadline and a default.
- Commitments (`approved commit`, `CI green`, `return to the issue`) arrive in M3 via
  `CommitmentGraph`. A hard violation becomes `verify` or `ask`; commitments are not a security
  boundary.
- The LAIX app kit — execution, proposal store, delivery — is **not used**. Works is the host and
  already owns those.

## Consequences

- Gates gain an explicit reason, confidence, alternatives and an audit record; the proof can show
  why a person was asked.
- One extra optional dependency and adapter surface, conformance-tested against recorded fixtures.
- LAIX is pre-1.0 (schema 0.8.0), so a version bump is a reviewed change, not a lockfile refresh.
- The default action policy returns `reason_code=policy_rule` and does not propagate
  `Decision.reversible`; Works derives urgency/risk from evidence and uses its own policy when
  richer reason codes are needed.
- Attention metrics and calibration are derived from events, not from agent prose.
- No second queue, proposal store, delivery path or ledger is introduced.

## Alternatives rejected

- **Hard-code richer gate logic in the supervisor**: repeats what LAIX already does and keeps the
  decision invisible in the proof.
- **Use the LAIX app kit for execution and storage**: creates a second source of truth beside
  `events.jsonl` and the ledger.
- **Let LAIX replace the verifier or path policy**: a decision layer is not evidence; safety and
  correctness must stay outside it.
- **Turn LAIX on directly**: without shadow replay and fail-closed fallback, a pre-1.0 policy change
  could silently widen a gate.
