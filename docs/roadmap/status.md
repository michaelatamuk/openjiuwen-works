# Status

> **Doc status:** active · **Owner:** Michael · **Last reviewed:** 2026-11-27

What is built and what is left. The live checklist is the
[2026 modernization plan](2026-modern-plan.md); this page is the one-screen answer, and the
[milestones](milestones/) are the design records.

## The loop is complete

The ten stages run end to end: intake, reproduce, plan, plan gate, build, check, proof, release gate,
deliver and confirm. The local daemon, the SPA, the scheduler, the proof and the two human gates are
in place. The deterministic demo runs without a model.

## Delivered

| Area | Evidence |
|---|---|
| The v0 loop (M0–M4) | [legacy plan](archive/plan-v4.md), [concepts](../guides/workflow/concepts.md) |
| Local daemon, API and SPA | [HTTP API](../reference/platform/http-api.md), [ADR 016](../adrs/016-local-daemon.md) |
| Scheduler and estimates (M21–M22) | [scheduler](../reference/platform/scheduler.md), [ADR 024](../adrs/024-scheduler-actor.md), [ADR 025](../adrs/025-ordering-cost-model.md) |
| Decision support (M23) | [ADR 026](../adrs/026-risk-is-evidence.md) |
| Per-repository parallelism (M24) | [ADR 027](../adrs/027-per-repo-parallelism.md) |
| CVE, measurement report, scan, monitor, specialists and benchmark (M25–M30) | [capabilities](../reference/capabilities/), [report](../reference/platform/report.md) |
| 2026 modernization | [plan](2026-modern-plan.md) — every checkbox is closed except one |

## Open

One checkbox is open in the 2026 plan:

- **M15.7 — network isolation for build commands.** Paths and commands are constrained; the network
  claim is not made. Deferred until a container or firewall-based runner is in scope. It does not
  block the local flow.

Anything not in that plan belongs in a new ADR or a new milestone, not in a silent edit.

## How to read the plans

- [2026 modernization plan](2026-modern-plan.md) — the live checklist and the acceptance gates.
- [Milestones](milestones/) — design records for the delivered passes.
- [Legacy plan v4.24](archive/plan-v4.md) — the original scope, invariants and rationale; archived.
- [Engineering standard](../guides/contributing/engineering-standard.md) — the bar every change meets.
