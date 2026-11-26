<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/ui/banner-dark.svg" />
    <img src="docs/ui/banner.svg" alt="openJiuwen Works — one signal in, a released fix out, back in the product" width="100%" />
  </picture>
</div>

# openJiuwen Works

**A local-first software factory.** A bug report goes in. A reproduced, tested and proven fix comes
out — with a person approving the plan and a person releasing the proven commit.

[![ci](https://github.com/michaelatamuk/openjiuwen-works/actions/workflows/ci.yml/badge.svg)](https://github.com/michaelatamuk/openjiuwen-works/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-6D28D9.svg)](LICENSE)

> A coding agent usually stops at a diff. Works carries the change through proof, review and release.

<div align="center">
  <img src="docs/ui/story.png" alt="The Story view: reported, picked up, confirmed, fixed and checked, with the release gate ready for a person" width="100%" />
</div>

## What it does

Writing the fix is the short part. Most of the time goes to triage, a plan, a review and proof that the
change is safe.

Works moves that work into one local engine and keeps the judgement with people. It reproduces the
problem, drafts a plan, builds in a disposable copy, checks the change, writes the proof, prepares the
release, delivers it and confirms the real result. Two decisions remain with people: **the plan** and
**the release**.

It runs on your machine: one daemon owns one home (`~/.works`), with no accounts and no hosted service.
Delivery ends at a change request; merge, deploy and close remain human actions.

## The two human gates

- **The plan gate.** A person approves the checks that will judge the change. The engine cannot approve
  itself, and an agent identity is refused.
- **The release gate.** A person approves the exact commit and proof. Delivery waits for that decision.

Everything else — reproduce, build, check, proof, delivery, confirmation — is automatic and recorded.

## The whole path

| Step | What happens | Who |
|---|---|---|
| **Signal** | A person, a tracker or a detector reports a problem. Duplicates are suggested, never merged by themselves. | anyone |
| **Reproduce** | The failing command must fail on the base commit; a fix is not attempted without it. | engine |
| **Plan** | A plan with steps, files and the checks that will judge it. | engine |
| **Plan gate** | The plan is approved, changed or rejected, with a name, a device and an expiry. | **you** |
| **Build** | A real builder edits a disposable worktree; every touched path is checked against policy. | engine |
| **Check** | Repository tests, an independent challenger, then the approved scenarios. | engine |
| **Proof** | One page bound to the exact diff by SHA-256: verdict, commands, policy, cost, risk, gaps. | engine |
| **Release gate** | Approve, hold or reject the released packet; a stale proof or an expired approval blocks it. | **you** |
| **Deliver** | A branch, one change request and one comment on the original report. | engine |
| **Confirm** | The released commit is re-checked by URL, command or preview; the result is kept beside the proof. | engine |

<div align="center">
  <img src="docs/deck/software-factory-flow.png" alt="The flow: signal, reproduce, plan, plan gate, build, check, proof, release gate, delivery and confirmation" width="100%" />
</div>

A blocked task stays blocked until a person changes the plan or the evidence. Nothing is retried
silently.

## Quick start (no model, no network)

```bash
uv sync --extra dev
python scripts/demo-ui.py
# use the path the script prints
uv run works --home /path/printed/by/demo ui
```

That opens `http://127.0.0.1:8765/` with five deterministic tasks — a known product report, a blocked
check and a task in the middle of the flow. It is local, deterministic and needs no model or network.

Add `--write` to report a new problem from the GUI. Creating a task never starts a run and never
approves a gate.

## Run it for real

Works keeps one home: `~/.works` (on Windows, `C:\Users\<you>\.works`), whatever directory you start
from. `--home` is for demos and tests, not daily use.

```bash
uv sync --extra server --extra providers   # daemon, UI and live providers
works daemon start --write                 # one daemon owns the home and the runs
```

Open `http://127.0.0.1:8765/`. Viewing on loopback needs no token; another device needs pairing
(`docs/guides/remote.md`).

### Through the browser

1. **Import** a ticket from GitHub, Jira or a detector, or **create** one by hand.
2. A run reproduces the problem and drafts a plan; the task waits at the plan gate.
3. Approve, hold or reject the plan on the task card.
4. Approve the plan and let it build, check and write the proof.
5. On the Release page, approve the packet, deliver the change and confirm the result.

### Through the terminal, a task from start to finish

```bash
works submit --repo /path/to/repo --product MyProduct --ref GH-42 \
  --title "The export drops the last column"

works run <task-id>                 # reproduce + draft a plan, then stop
works approve <task-id> --gate plan # the first human decision

works run <task-id> --live --scenarios scenarios.yaml
works release <task-id>             # the read-only release packet
works approve <task-id> --gate release

works deliver <task-id> --provider github
works confirm <task-id> --url https://app.example/health \
  --expect-status 200 --expect-commit <sha> --provider github
```

Use `--trace fixtures/traces/fix-add.json` instead of `--live` for a deterministic run with no model.
The live builder needs a provider key (`ANTHROPIC_API_KEY` or your configured provider); see
`docs/guides/live-harness.md`.

## Scheduling: what runs next

When more than one thing is ready, a local scheduler decides what runs next — and says why on every
card.

```bash
works scheduler status
works scheduler enable
works scheduler pause --reason "deploying"
works scheduler tick
```

<div align="center">
  <img src="docs/deck/software-factory-queue.png" alt="The queue: new work waits in one line, a helper asks four questions, and two moments belong to a person" width="100%" />
</div>

It is off by default. Approvals stay with people, one project runs one job at a time, and a started
run is allowed to finish. When history is thin the estimate comes from the plan; with history it comes
from similar past jobs. Estimates are ranges, not deadlines.

```bash
works estimate backtest      # calibration: coverage and tail misses by group
works estimate promotion     # is the learned order ready to promote?
```

A learned order only starts after a named person records the evidence with `works estimate promote`;
until then the rules decide. Details: `docs/reference/scheduler.md`.

## Capabilities

| Area | What you get |
|---|---|
| **Queue** | One line, typed reasons for waiting, duplicate suggestions, pause/resume and an opt-in scheduler. |
| **Estimates** | Expected and worst-case time and cost from similar jobs, the plan or a default; a calibration check and a promotion guard. |
| **Gates** | Plan and release decisions bound to a saved artefact, with a person, a device, an expiry and a complete history. |
| **Proof** | One page bound to the diff; artifacts, the event chain, cost, risk and what was not covered. |
| **Delivery** | A branch, one change request and one source comment; repeating it does not duplicate them. |
| **Confirmation** | HTTP with an expected status, text and commit; a command in a fresh copy; or a browser preview. A retry that changes its answer is reported as unstable. |
| **Intake** | GitHub Issues, Jira, detector alerts and people; product-to-repository map. |
| **UI** | Queue, Story, Evidence, Release, Session and Settings, served by the daemon. |
| **Surfaces** | CLI, HTTP API and an MCP server for agents; the gates stay human on every surface. |
| **Checks** | Repository tests, an independent challenger, approved scenarios and an optional Docker verifier. |

## Status

Stages 1–10 of the flow are built: signal, reproduce, plan, plan gate, build, check, proof, release
gate, delivery and confirmation. The queue and scheduler are built; estimates and the shadow order are
built. The single deferred item is network isolation for build commands (`M15.7`).

CI runs lint, types, the typing ratchet, unit and contract tests with a coverage floor, the web suite,
Playwright journeys, benchmarks and supply-chain checks on Linux and Windows.

## Documentation

- [`docs/guides/how-a-fix-flows.md`](docs/guides/how-a-fix-flows.md) — the flow in plain words, with
  the two human gates.
- [`docs/design/2026-modern-plan.md`](docs/design/2026-modern-plan.md) — the live plan and checkboxes.
- [`docs/design/2026-m21-scheduler.md`](docs/design/2026-m21-scheduler.md) and
  [`docs/design/2026-m22-estimates.md`](docs/design/2026-m22-estimates.md) — the queue and the numbers.
- [`docs/reference/scheduler.md`](docs/reference/scheduler.md) and
  [`docs/reference/inbox.md`](docs/reference/inbox.md) — scheduler and duplicate triage reference.
- [`docs/guides/runbook.md`](docs/guides/runbook.md) — known failures and the first response.
- [`docs/guides/remote.md`](docs/guides/remote.md) — another device without exposing the port.
- [`docs/guides/live-harness.md`](docs/guides/live-harness.md) — a real builder.
- [`docs/guides/intake.md`](docs/guides/intake.md) — trackers, detectors and the product map.
- [`docs/reference/proof.md`](docs/reference/proof.md) — what the proof contains and how to verify it.
- [`docs/adrs/`](docs/adrs/) — the decisions that are expensive to reverse.

## Development

```bash
make check          # ruff, format, mypy, typing ratchet, prompts, evals, tests with coverage
make integration    # the whole loop, no model
make bench          # CLI, status and evidence budgets
```

The web app is React/Vite in `web/`; the built assets under
`src/works/interfaces/ui/static/dist` are committed, so `works ui` needs no Node at runtime. After
changing the UI, run `cd web && npm ci && npm run test && npm run build`.

## Repository map

```text
src/works/domain/        task, event, run, plan, evidence, policy, flow
src/works/application/   supervisor, planning, execution, delivery, approvals, scheduling
src/works/adapters/      queue, git, harness, processes
src/works/interfaces/    CLI, HTTP API, UI assets and daemon
web/src/                 React app: queue, story, evidence, release, session, settings
flows/                   the fix-issue flow as a node graph
fixtures/                planted-bug repo, scenarios, traces and decision cases
tests/                   unit, contract, integration and end-to-end
docs/                    guides, reference, design and ADRs
scripts/                 demo, benchmark, checks and deck
```

## License

Apache-2.0. See [`LICENSE`](LICENSE).
