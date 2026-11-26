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

> Most coding agents stop at a diff. Works carries the fix to release — and brings the proof with it.

<div align="center">
  <img src="docs/ui/story.png" alt="The Story view: reported, picked up, confirmed, fixed and checked, with the release gate ready for a person" width="100%" />
</div>

## What it does

Writing the fix is the short part. The waiting is the work: waiting for triage, for a plan, for a
review, for someone to prove the change is safe.

Works moves the waiting into one local engine and keeps the judgement with people. It reproduces the
problem, drafts a plan, builds in a disposable copy, checks the change, writes the proof, prepares the
release, delivers it and confirms the real result. You make two decisions: **the plan** and **the
release**.

## The two moments that stay yours

- **The plan gate.** A person approves the checks that will judge the change. The engine cannot approve
  itself, and an agent identity is refused.
- **The release gate.** A person approves the exact commit and proof. Delivery waits for that decision.

Everything else — reproduce, build, check, proof, delivery, confirmation — is automatic and recorded.

## The whole path

| Step | What happens | Who |
|---|---|---|
| **Signal** | A person, a tracker or a detector reports a problem. Duplicates are suggested, never merged by themselves. | anyone |
| **Reproduce** | The failing command must fail on the base commit. No reproduction, no fix. | engine |
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

## Try it in 60 seconds (no model, no network)

```bash
uv sync --extra dev
python scripts/demo-ui.py
# use the path the script prints
uv run works --home /path/printed/by/demo ui
```

That opens `http://127.0.0.1:8765/` with five deterministic tasks — a known product report, a blocked
check and a task in the middle of the flow. It is local, free and repeatable.

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

### Through the terminal, one task start to finish

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

## The queue, without the drama

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

It is off by default. It never approves a plan or a release, never runs two jobs in one project, and
never preempts a started run. When the history is thin it estimates from the plan; when it has history
it compares similar past jobs; it never promises a deadline.

```bash
works estimate backtest      # is the estimate honest? coverage and tail misses by group
works estimate promotion     # has a learned order earned a vote?
```

A learned order only starts after a named person records the evidence with `works estimate promote`;
until then the rules decide. Details: `docs/reference/scheduler.md`.

## What is in the box

| Area | What you get |
|---|---|
| **Queue** | One line, typed waiting reasons, duplicate suggestions, pause/resume, an opt-in scheduler. |
| **Estimates** | p50/p90 time and cost from similar jobs, the plan or a static prior; a backtest and a promotion guard. |
| **Gates** | Plan and release decisions bound to an artefact, with a person, a device, an expiry and an appendix-only history. |
| **Proof** | One page bound to the diff; artifacts, event chain, cost, risk and residual gaps. |
| **Delivery** | A branch, one change request and one source comment; idempotent by markers. |
| **Confirmation** | HTTP with expected status/text/commit, a command in a fresh copy, or a Playwright preview; retries report instability, never a silent green. |
| **Intake** | GitHub Issues, Jira, detector alerts and people; product-to-repository map. |
| **UI** | Queue, Story, Evidence, Release, Session and Settings, served by the daemon. |
| **Surfaces** | CLI, HTTP API and an MCP server for agents — none of them can approve a gate. |
| **Checks** | Repository tests, an independent challenger, approved scenarios, a Docker verifier option. |

## What it deliberately does not do

- no cloud, no accounts, no hosted queue — one daemon owns one home;
- no auto-merge, auto-deploy or auto-close;
- no automatic approval of either gate, at any level;
- no second job in the same project, and no preemption of a started run;
- no claim of network isolation for build commands yet (deferred; it needs an OS sandbox).

## Status

Stages 1–10 of the flow are built: signal, reproduce, plan, plan gate, build, check, proof, release
gate, delivery and confirmation. The queue and scheduler are built; estimates and the shadow order are
built. The single deferred item is network isolation for build commands (`M15.7`).

CI runs lint, types, the typing ratchet, unit and contract tests with a coverage floor, the web suite,
Playwright journeys, benchmarks and supply-chain checks on Linux and Windows.

## Documentation

- [`docs/guides/how-a-fix-flows.md`](docs/guides/how-a-fix-flows.md) — the flow in plain words, with
  the two human moments.
- [`docs/design/2026-modern-plan.md`](docs/design/2026-modern-plan.md) — the live plan and checkboxes.
- [`docs/design/2026-m21-scheduler.md`](docs/design/2026-m21-scheduler.md) and
  [`docs/design/2026-m22-estimates.md`](docs/design/2026-m22-estimates.md) — the queue and the numbers.
- [`docs/reference/scheduler.md`](docs/reference/scheduler.md) and
  [`docs/reference/inbox.md`](docs/reference/inbox.md) — scheduler and duplicate triage reference.
- [`docs/guides/runbook.md`](docs/guides/runbook.md) — known failures and the first response.
- [`docs/guides/remote.md`](docs/guides/remote.md) — another device without opening the world.
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
