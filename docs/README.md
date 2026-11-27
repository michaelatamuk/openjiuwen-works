# Documentation

Start with the question you have. A page whose status is not `active` carries a banner under its H1;
`archive/` is historical and read-only. A new page belongs in the section that matches the reader's
question, not in the section that matches the file's genre.

## Start here

- [Concepts: how a fix gets made](guides/workflow/concepts.md) — the ten stages and the two human gates.
- [Status](roadmap/status.md) — what is built and the one open item.
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
  [typing ratchet](reference/generated/typing-baseline.json); the
  [directory README](reference/generated/README.md) names the script for each one.

## Understand the design

- [Architecture](architecture.md) — processes, layers, one run, data and invariants.
- [Planner](reference/lifecycle/planner.md) — the planning component and its delivery phases.
- [Architecture decisions](adrs/README.md) — one record per expensive choice.
- [Legacy plan v4.24](roadmap/archive/plan-v4.md) — the original scope and rationale; archived.
- Strategy: [positioning](strategy/positioning.md),
  [competitors](strategy/competitor-analysis.md),
  [feature recommendations](strategy/feature-recommendations.md),
  [Mira](strategy/mascot.md).

## Contribute

- [Engineering standard](guides/contributing/engineering-standard.md) — the bar every change meets.
- [Docs conventions](guides/contributing/docs.md) — where a page goes, the manifest and the checks.
- [Layout](guides/contributing/layout.md) — where a new module, route or screen goes.
- [Typing](guides/contributing/typing.md) — the `Any` ratchet and how to change it.
- [Assets](assets/README.md) — images, slides and the film; no single-file directories.
- [Contributing](../CONTRIBUTING.md) — setup, rules and the PR checklist.
- [Archive](archive/) and [roadmap archive](roadmap/archive/) — historical reviews, demos and plans;
  read-only.
