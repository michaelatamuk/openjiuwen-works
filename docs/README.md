# Documentation

Start with the question you have. Every page below is current; `archive/` is historical and
read-only. A new page belongs in the section that matches the reader's question, not in the
section that matches the file's genre.

## Start here

- [Concepts: how a fix gets made](start/concepts.md) — the ten stages and the two human gates.
- [Quickstart](../README.md#try-it) — run the deterministic demo without a model.

## Do a task

- Workflow: [intake](guides/workflow/intake.md), [release](guides/workflow/release.md),
  [verification](guides/workflow/verification.md), [readiness](guides/workflow/readiness.md),
  [waiting and dispatch](guides/workflow/waiting-and-dispatch.md), [local GUI](guides/workflow/ui.md).
- Operations: [runbook](guides/operations/runbook.md), [remote clients](guides/operations/remote.md),
  [supply chain](guides/operations/supply-chain.md).
- Integrations: [live harness](guides/integrations/live-harness.md),
  [JiuwenSwarm](guides/integrations/swarm.md), [PPMA memory](guides/integrations/ppma.md),
  [LAIX](guides/integrations/laix.md), [agent-core team](guides/integrations/agent-core.md).

## Look up a fact

- Lifecycle: [signal](reference/lifecycle/signal-intake.md) →
  [reproduce](reference/lifecycle/reproduce.md) → [plan](reference/lifecycle/planning.md) →
  [build](reference/lifecycle/build.md) → [check](reference/lifecycle/check.md) →
  [proof](reference/lifecycle/proof.md) → [gates](reference/lifecycle/gates.md) →
  [deliver](reference/lifecycle/deliver.md) → [confirm](reference/lifecycle/confirm.md).
- Platform: [HTTP API](reference/platform/http-api.md), [scheduler](reference/platform/scheduler.md),
  [reliability](reference/platform/reliability.md), [prompts](reference/platform/prompts.md),
  [report](reference/platform/report.md).
- Capabilities: [CVE](reference/capabilities/cve.md), [scan](reference/capabilities/scan.md),
  [monitor](reference/capabilities/monitor.md), [reporter](reference/capabilities/reporter.md),
  [specialists](reference/capabilities/specialists.md), [bench](reference/capabilities/bench.md),
  [features](reference/capabilities/features.md), [inbox](reference/capabilities/inbox.md).
- Generated, do not edit: [OpenAPI](reference/generated/openapi.json),
  [baseline](reference/generated/openapi.baseline.json),
  [typing ratchet](reference/generated/typing-baseline.json).

## Understand the design

- [The plan](roadmap/plan.md) — vision, invariants, architecture and the engineering standard.
- [Planner](architecture/planner.md) — the planning contract and its delivery phases.
- [Architecture decisions](adrs/README.md) — one record per expensive choice.
- [2026 modernization plan](roadmap/2026-modern-plan.md) and
  [milestones](roadmap/milestones/) — what was built and why.
- Strategy: [positioning](strategy/positioning.md),
  [competitors](strategy/competitor-analysis.md),
  [feature recommendations](strategy/feature-recommendations.md).

## Contribute

- [Layout](guides/contributing/layout.md) — where a new module, route or screen goes.
- [Typing](guides/contributing/typing.md) — the `Any` ratchet and how to change it.
- [Contributing](../CONTRIBUTING.md) — setup, rules and the PR checklist.
- [Archive](archive/) — historical reviews and demos; read-only.
