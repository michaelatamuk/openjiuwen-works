# ADR-010 — A factory is a task graph with waits, not an org chart of agents

**Status:** accepted · 2026-11-21

## Context

Two production descriptions converge: OpenAI's Performance Factory and Alex Greenshpun's
Outsourcerer/Total Recall setup. Both run agents over a **persistent task** whose state, findings
and evidence live outside any single agent. Both keep a person only where judgement changes the
outcome, and both treat "done" as something an independent party confirms.

Our M0.5 loop already has a task state machine, evidence and gates, but `BLOCKED` is terminal and a
run is one-shot. That cannot represent "waiting for review", "waiting for CI", or "waiting for a
deployment".

## Decision

- The factory is a **task graph**: explicit states, allowed transitions, findings and wake events.
- Waiting is a first-class state (`waiting_review`, `waiting_ci`, `waiting_deploy`), not `blocked`.
  Every wait has a wake event, a deadline and a default; `works doctor` reports stranded waits.
- A dispatcher claims ready tasks and advances one step. It is safe to kill and never runs a task
  twice.
- Findings and evidence are structured records outside the agent context; agent prose is never
  parsed into a decision.
- No agent grades its own work: builders, challengers and verifiers are separate roles, preferably
  on different providers.
- Attention is the primary metric: human touches, waiting time, agent-hours per human-hour,
  rework, fix share. Agent count is not a target.
- Prompts are versioned files with a hash recorded in the run and proof.

## Consequences

- More states and transitions, and a dispatcher; cheap in code, expensive to retrofit after a GUI.
- A task can live for days across a review and a deployment, so idempotency and event replay are
  mandatory.
- The two human gates remain; autonomy expands only after evals and a green escape window.
- This supersedes the "blocked is terminal" simplification in the M0.5 supervisor.

## Alternatives rejected

- **Agent org chart**: roles such as "CTO agent" cap the system at a human metaphor and add no
  mechanism.
- **One long-running agent**: loses resumability, hides findings in context and makes independent
  review impossible.
- **Always autonomous merge**: the evidence from both factories is that review, not diagnosis, is
  the bottleneck; 15 exact agent-authored PRs out of ~400 proposed fixes is not a reason to remove
  the gate.
