# ADR-005 — The verifier is independent in runtime and provider

**Status:** accepted · 2026-11-21

## Context

If the same model, provider and process judge the change they produced, failures correlate: the
same blind spot writes the bug and approves it. A verdict from such a setup is a formality.

## Decision

- The verifier runs in a separate container, with no builder transcript.
- It uses a different provider from the builder; model ids are recorded per run.
- It sees the worktree read-only, the scenario, and the reproduced behaviour — never the raw issue
  text, never the builder's reasoning.
- The verdict is mechanical: all P0 pass, P1 ≥ 80%, else block.
- Specificity is tested with sneaky patches: a change that satisfies the literal issue but breaks
  adjacent behaviour must turn a P0 red.

## Consequences

- Two providers to configure and pay for; worth it for an independent signal.
- Scenarios must be self-contained, because the verifier does not see the issue text.
- Calibration (judge vs human) becomes a required gate, not an optional check.

## Alternatives rejected

- **Same provider, different prompt**: cheap, correlated, and it hides the failure we care about.
- **Human-only verification**: honest, but it is the bottleneck we set out to remove.
