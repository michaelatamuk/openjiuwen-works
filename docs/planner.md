# Planner

Works should plan better than a single prompt and stay auditable. This document is the design
contract and the delivery plan for the planner. It is intentionally broader than the first
implementation; each phase lands with tests and evidence.

## Delivered

This change lands the first two phases:

- versioned plan artefacts (`queue/<task>/plans/vN.json` and `.md`), hashes and approval binding;
- deterministic, shadow, assisted and deep modes;
- a read-only OpenJiuwen planner and independent critic with versioned prompts;
- plan linting, planner settings/health, `works plan` draft/show/lint/diff;
- the approved plan brief is injected into the builder and the Swarm adapter;
- the plan id/hash/planner cost is part of the run record and proof;
- the Session view shows the plan card with steps, planner, lint and hash.

Still open: `works plan eval`, replanning, approved-plan memory, auto mode, spec-driven artefacts,
alternative plans and preview/simulation.

## Why

Other AI factories mostly plan with a model and then enforce the result with deterministic rails:

- **Factory.ai Missions** use an orchestrator to turn a request into features, milestones and a
  validation contract; a person approves the plan. Orchestration lives mostly in prompts/skills,
  with a thin deterministic layer for bookkeeping and blocking.
- **Devin** has a read-only Plan mode that writes a Markdown plan and waits for approval.
- **OpenHands** ships a dedicated planning agent that can read the repo and write only `PLAN.md`,
  then hands the plan to an execution agent.
- **SWE-agent** has no explicit planner; planning is implicit in its ReAct loop.
- **GitHub Copilot Workspace** generated an editable spec and plan, then implemented it.
- **Kiro / Spec Kit / Tessl** make requirements, design and tasks first-class artefacts with human
  review gates.
- **Stripe Minions** use blueprints: agentic nodes for planning/implementation/fixes, deterministic
  nodes for lint, tests, push and CI policy. The harness, not the prompt, enforces the order.

The lesson is not "make planning deterministic" or "let the model plan". The strong pattern is:

> model proposes, deterministic contract validates, a person approves, the harness executes, and
> every deviation is recorded.

Works already has the deterministic contract (flow + scenario set + policy + gates). The planner
adds the missing adaptive layer without giving up that contract.

## Principles

1. **The flow is the contract.** A planner cannot remove or reorder required flow nodes. It can add
   steps inside them, name files, propose tests, surface risks and ask questions.
2. **Plan is a versioned artefact.** Every draft is immutable, hash-addressed and downloadable as
   JSON and Markdown. Approval names the exact plan hash, base commit and checks SHA.
3. **A person owns the plan gate.** A model may recommend; it cannot approve. Auto-approval is a
   later, calibrated mode for low risk only.
4. **Deterministic nodes never call a model.** Reproduction, tests, policy, lint, budget and push
   stay deterministic. The planner only produces text; the supervisor executes code.
5. **Fail closed.** An invalid, stale or unapproved plan blocks the task. A planner failure never
   turns into a silent fake plan.
6. **Cost is evidence.** Planner and critic tokens/USD are recorded separately from builder and
   verifier cost.
7. **Plan once, execute deliberately.** The plan is a contract for the run; deviations are events,
   not quiet edits.

## Plan modes

| Mode | What runs | Gate | Use |
|---|---|---|---|
| `deterministic` | flow + scenario skeleton only | human | audit-first, no model cost, current behaviour |
| `shadow` | deterministic is used; a model proposal is stored beside it for comparison | human on deterministic | measure planner quality without changing outcomes |
| `assisted` | model proposal merged with the deterministic skeleton and linted | human | default recommendation for real work |
| `deep` | model proposal + independent critic + lint | human, higher evidence | ambiguous or high-risk changes |
| `auto` | later: assisted/deep plus calibrated confidence and risk policy | deterministic policy for low risk, human for high risk | after shadow evidence |

`deterministic` stays the default until the other modes have evidence.

## Pipeline

```
task + flow + scenario set + repo state + memory
        │
        ▼
1. intake pack       bounded, deterministic context: task, flow, scenarios, file tree,
                     readiness, risk, policy, recall, recent findings
        │
        ▼
2. clarify           optional model questions; answers or explicit assumptions are recorded
        │
        ▼
3. draft             deterministic skeleton, then optional model proposal inside it
        │
        ▼
4. merge             required nodes preserved; model steps mapped to nodes; order fixed by flow
        │
        ▼
5. lint              schema, node coverage, P0 coverage, path policy, forbidden commands,
                     budget, test-edit policy, unknown steps, rollback
        │
        ▼
6. critique          deep mode: independent critic with rubric and findings
        │
        ▼
7. approve           human gate; approval binds plan hash + base commit + checks SHA
        │
        ▼
8. freeze            immutable plan version; run follows it and records deviations
        │
        ▼
9. replan            on a blocked run or changed base, draft a new version and re-approve
```

## Plan artefact

```json
{
  "schema_version": 1,
  "plan_id": "p-<task>-v1",
  "task_id": "t-...",
  "version": 1,
  "status": "draft|validated|approved|frozen|superseded|shadow",
  "created_at": "...",
  "flow": "fix-issue",
  "product": "openjiuwen",
  "base_commit": "sha",
  "checks_sha": "sha",
  "scenario_set": "path",
  "scenario_ids": ["..."],
  "summary": "one paragraph",
  "assumptions": ["..."],
  "open_questions": ["..."],
  "steps": [
    {
      "id": "s1",
      "node": "build",
      "title": "Change add to return a + b",
      "intent": "why and how",
      "files": ["calc/core.py"],
      "commands": [],
      "done_when": "calc tests pass",
      "risk": "low",
      "depends_on": [],
      "reversible": true
    }
  ],
  "risks": ["..."],
  "verification": ["pytest", "P0 scenarios"],
  "rollback": "revert the worktree commit",
  "estimated_tokens": 40000,
  "estimated_minutes": 12,
  "provenance": {
    "mode": "assisted",
    "planner": "native",
    "provider": "deepseek",
    "model": "deepseek-chat",
    "prompt_sha256": "...",
    "tokens": 1234,
    "usd": 0.001,
    "duration_ms": 8400,
    "fallback": false,
    "error": null
  },
  "validation": {"ok": true, "errors": [], "warnings": [], "checks": ["..."]},
  "critique": {"allow": true, "score": 0.83, "findings": [], "concerns": []},
  "hash": "sha256"
}
```

The hash covers the plan content, task, base commit, checks SHA and scenario set. It does not cover
status, approval, validation or critique, so those can be added without invalidating the content.

## Modes and providers

Planner settings live beside builder settings:

- `planner_mode`: `deterministic` (default), `shadow`, `assisted`, `deep`.
- `planner_provider` and `planner_model`: used for the proposal.
- `planner_critic_provider` and `planner_critic_model`: used for `deep` critique.
- Credentials stay in the environment and are never stored in the browser.

Planner providers reuse the OpenJiuwen harnesses:

- `claudecode` in `plan` permission mode (read-only exploration);
- `native` with a read-only `core.sys_operation` rail;
- `dsh` / `codex` once read-only planning is proven.

JiuwenSwarm is not a planner provider. It can supply a plan through its own adapter only if that
adapter grows a `plan` contract; until then it remains a builder runtime. Works' own read-only
planner can still draft the plan before a Swarm build, because the plan gate belongs to Works, not
to the builder.

## Context pack

The planner receives a bounded, reproducible pack:

- task source, title, kind, budget and policy;
- flow nodes and gates;
- scenario ids, priorities and descriptions;
- repository file tree (bounded), README, manifests and test file names;
- readiness status and checks SHA;
- risk rating and required owners;
- memory recall (PPMA) when configured;
- recent findings, prior plan versions and their critiques;
- explicit `do_not_touch` paths and test-edit policy.

The agentic planner may read more files through its read-only tools. Every file it reads and every
tool call is recorded in the plan provenance, not hidden.

## Validation

The plan linter is deterministic and runs before any model critic:

- every required flow node has at least one step; no unknown nodes;
- P0 scenarios appear in verification;
- paths are relative, inside the repo, and respect policy/deny lists;
- no test edits unless the task is `check-change` or the plan explicitly requests an exception;
- no destructive or network-side-effect commands without a recorded approval;
- estimated cost fits the task budget;
- summary, done-when and rollback are present;
- open questions are surfaced, never ignored.

A failed lint blocks the plan gate. The model cannot override a lint error.

## Execution contract

The supervisor executes flow nodes, not free-form plan steps. Plan steps are attached to nodes for
progress and evidence. When the builder does something outside the plan, the run records a
`plan.deviation` event with the paths and reason. A deviation is not automatically a failure, but it
is visible in the proof.

On resume, the run compares the stored plan hash, base commit and checks SHA. A changed contract
requires a new plan version and a new approval.

## Replanning

A new plan version is drafted when:

- the base commit or checks SHA changes;
- lint fails in a way a person chooses to fix;
- the builder is blocked and a finding changes the approach;
- the critic rejects the plan;
- the task scope changes.

The old version is marked `superseded`, never deleted. Re-approval is required for a material change.

## CLI

```
works plan <task> [--scenarios PATH] [--mode deterministic|shadow|assisted|deep] [--json]
works plan show <task> [--version N] [--json]
works plan lint <task>
works plan approve <task> [--plan-id ID]
works plan diff <task> [--from N] [--to N]
```

`works approve --gate plan` remains an alias for approval, but must name the plan hash or accept the
latest version explicitly.

## API and UI

- `GET /api/plan?task_id=...` returns the latest plan and its validation/critique.
- `POST /api/plan/draft` (write mode) drafts a new version for the given task and scenario set.
- The Story/Thread plan card shows: summary, steps by flow node, files, done-when, risks,
  verification, assumptions, open questions, planner model/cost, lint result, critic result, and
  Approve / Reject / Regenerate.
- Settings gets a Planner section with mode, provider/model, critic provider/model and availability.
- A plan diff view compares versions and the deterministic skeleton.

## Telemetry and evaluation

Record for every plan:

- mode, provider, model, prompt hash, tokens, USD, duration, fallback/error;
- lint errors/warnings and critic score;
- approval identity and time;
- execution deviations and their outcome;
- replan count and reasons;
- proof outcome (proved/blocked) and verification share.

`works plan eval` will replay historical tasks through planner candidates, like `works decision
replay`: deterministic baseline, shadow proposal and candidate planner. The goal is measured plan
quality, not vibes.

## Security and policy

- Planner tools are read-only; the only writable artifact is its own output channel.
- The planner never receives credentials; the harness injects them.
- Plans cannot authorize policy exceptions, test edits, deployments or network effects.
- Skill/MCP/prompt injection in the repository is treated as untrusted data.
- High-risk paths require the same owners and human gate as the builder.

## Delivery plan

### Phase 1 — versioned deterministic plan and contract

- Plan models, hash, JSON/Markdown artefact, version store.
- Deterministic planner produces one step per flow node with scenario coverage.
- Plan linter and approval binding.
- `works plan` draft/show/lint/approve/diff.
- Supervisor emits `plan.drafted` with `plan_id`, `version`, `hash`.
- Tests and docs.

Acceptance: deterministic runs behave as before; every plan is downloadable and approval is bound
to a hash; an invalid plan blocks.

### Phase 2 — assisted model planner

- Read-only harness planner and versioned `plan.md` prompt.
- Context pack, JSON parsing, merge and fallback policy.
- Settings: mode/provider/model; health and UI.
- `shadow` and `assisted` modes.
- Record planner tokens/USD/prompt hash.
- Tests with a fake planner and one live fixture run.

Acceptance: assisted plan is linted, stored, approved by hash and executed; a planner failure blocks
without a fake plan; shadow proposals never change execution.

### Phase 3 — deep critique and clarify

- Independent critic with rubric and findings.
- `deep` mode and plan quality score.
- Clarifying questions and assumptions.
- Plan diff against the deterministic skeleton.
- UI plan card with approve/reject/regenerate.

Acceptance: critic rejection blocks; findings are in the proof; a person can compare versions.

### Phase 4 — replanning, memory and evaluation

- Replan on changed base/checks/blocked findings.
- Approved-plan memory and reuse.
- `works plan eval` replay and dashboards.
- `auto` mode only after shadow calibration and only for low risk.

Acceptance: measured planner quality, no silent auto-approval, every replan keeps history.

### Phase 5 — "much more"

- Spec-driven mode: requirements/design/tasks artefacts for larger features.
- Alternative plans (A/B) with trade-off table.
- Test-first planning and scenario generation.
- Risk/rollback simulation and budget forecast.
- Plan drift detection and execution guardrails.
- Multi-repo and cross-service dependency plans.

## Non-goals

- Replacing the flow contract with free-form model steps.
- Letting the planner approve its own plan.
- Running arbitrary plan commands in the host.
- Storing credentials or raw secrets in plan artefacts.
- Hiding planner cost or failures.
