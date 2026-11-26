<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/ui/banner-dark.svg" />
    <img src="docs/ui/banner.svg" alt="openJiuwen Works — one signal in, a released fix out, back in the product" width="100%" />
  </picture>
</div>

# openJiuwen Works

**A local-first software factory for teams whose review queue, not their typing speed, is the
bottleneck.** A report arrives. Works reproduces it, plans the change, builds it in a disposable copy
and writes the proof; people make the two decisions that matter.

[![ci](https://github.com/michaelatamuk/openjiuwen-works/actions/workflows/ci.yml/badge.svg)](https://github.com/michaelatamuk/openjiuwen-works/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-6D28D9.svg)](LICENSE)

<sub>v0.0.1 · pre-release</sub>

> Works carries a change through proof, review and release.

## What it does

- **Reproduces the problem** on the current code before anything changes.
- **Plans the change** and the checks that will judge it.
- **Builds in a disposable copy**, leaving your working tree clean.
- **Writes the proof**: one page tied to the exact change — commands, verdict, cost, risk and what was
  not covered.
- **Delivers and confirms**: a change request, one comment on the original report, then a fresh check
  of the real result.

The difference is in the binding: the proof is tied to the commit and re-verified at release, and the
checks are read from the base commit, so the change cannot edit its judge.

## One screen, the whole task

<div align="center">
  <img src="docs/ui/story.png" alt="One task from report to release: the route, the checks and the next step, with the release gate ready for a person" width="100%" />
</div>

The report, the route, the checks and the next step are in one place; the proof is one click away.
[Watch the 45-second film](docs/video/openjiuwen-works-two-mondays.mp4).

## Two decisions stay with people

- **The plan.** A person approves the checks that will judge the change.
- **The release.** A person approves the exact commit and its proof. Delivery waits for that decision.

Everything between the two decisions is automatic and recorded.

## How it works

| Phase | What happens | Who |
|---|---|---|
| **Understand** | A report arrives from a person, a tracker or a monitor. Works reproduces the problem on the current code. | Works |
| **Agree** | Works drafts a plan and the checks. A person approves, changes or rejects it. | **you** |
| **Change** | Works builds in a disposable copy and runs the approved checks. | Works |
| **Prove** | The evidence page is written and tied to the exact change. | Works |
| **Release** | A person approves the proof. Works delivers the change and confirms the real result. | **you**, then Works |

<div align="center">
  <img src="docs/deck/software-factory-flow.png" alt="The flow: signal, reproduce, plan, plan gate, build, check, proof, release gate, delivery and confirmation" width="100%" />
</div>

Every phase is recorded. A failed check or a mismatched proof returns the task to a person.

## When several things are ready

One queue, one job per project. Works shows why each task is waiting: a free slot, your decision, the
day's budget or the machine being busy.

<div align="center">
  <img src="docs/deck/software-factory-queue.png" alt="The queue: new work waits in one line, a helper asks four questions, and two decisions belong to a person" width="100%" />
</div>

The queue is optional and off by default. The plan and release decisions remain with people, and a
started run finishes.

## Try it

The demo is local and deterministic; it runs without a model or network.

```bash
git clone https://github.com/michaelatamuk/openjiuwen-works.git
cd openjiuwen-works
uv sync --extra dev
python scripts/demo-ui.py
# open the path the script prints
uv run works --home /path/printed/by/demo ui
```

That opens the app at `http://127.0.0.1:8765/` with five example tasks, including one waiting at the
release gate.

## Use it on your project

```bash
uv sync --extra server --extra providers
uv run works daemon start --write
```

Open `http://127.0.0.1:8765/` and:

1. **Import** a ticket from GitHub, Jira or a monitor, or **create** one.
2. Let Works reproduce it and draft a plan.
3. **Approve the plan**, then let Works build, check and write the proof.
4. **Approve the release**, deliver the change and confirm the result.

Requirements: Python 3.12+, `uv`, git and port 8765; Node only for UI development. A measured run on
the fixture costs $0.09 with the builder and $0.19 with an independent challenger, in 90–120 s; daily
and per-run limits live in the scheduler policy (`dispatch.yaml`).

A provider key is needed for the live builder; trace mode runs without a model — see
[`docs/guides/live-harness.md`](docs/guides/live-harness.md). The CLI follows the same two decisions;
`works --help` lists the commands.

## Built for one machine

Works runs on your machine: one daemon, one home (`~/.works`). Source, diffs and proofs stay there;
only your model provider receives the context the builder sends. The builder runs with your OS
permissions, so use a repository you trust. The plan and release decisions are human; one project runs
one job at a time. Delivery creates a change request; merge, deploy and close remain your decisions.

## Documentation

- [`docs/guides/how-a-fix-flows.md`](docs/guides/how-a-fix-flows.md) — the flow in plain words.
- [`docs/guides/runbook.md`](docs/guides/runbook.md) — what to do when something goes wrong.
- [`docs/reference/proof.md`](docs/reference/proof.md) — what the proof contains.
- [`docs/guides/intake.md`](docs/guides/intake.md) — trackers, monitors and your products.
- [`docs/guides/remote.md`](docs/guides/remote.md) — another device without exposing the port.
- [`docs/video/openjiuwen-works-two-mondays.mp4`](docs/video/openjiuwen-works-two-mondays.mp4) — the
  flow in motion.
- [`docs/deck/`](docs/deck/) — slides and diagrams.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
