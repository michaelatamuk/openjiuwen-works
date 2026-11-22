<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/ui/banner-dark.svg" />
    <img src="docs/ui/banner.svg" alt="openJiuwen Works — one signal in, a released fix out, back in the product" width="100%" />
  </picture>
</div>

# openJiuwen Works

**A local-first software factory.** A bug report goes in. A reproduced, tested and proven fix comes out - with a person approving the plan and a person releasing the proven commit.

[![ci](https://github.com/michaelatamuk/openjiuwen-works/actions/workflows/ci.yml/badge.svg)](https://github.com/michaelatamuk/openjiuwen-works/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-6D28D9.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.12-3776AB.svg)](pyproject.toml)

**Local-first preview** · proof before release · the plan gate is live, release is next

> Most coding agents stop at a diff. Works carries the fix to release — and brings the proof with it.

<div align="center">
  <img src="docs/ui/story.png" alt="openJiuwen Works Story view: Reported → Picked up → Confirmed → Fixed → Checked, with Mira at the ready-to-release gate and Evidence one click away" width="100%" />
</div>

## Reports in. Releases out.

A bug report waits: for triage, for an agent's answer, for a reviewer, for someone to prove the change works. Writing the fix is the short part.

## Built to ship.

**A factory that turns a report into a released fix — with proof you can inspect.**

Works moves the waiting into an engine and keeps the judgement with people:

- **Reproduce before fixing.** A deterministic command must fail on the base commit. No failing reproduction, no fix.
- **Two human gates in the design.** The plan gate and the release gate are live; the engine never
  approves itself, and delivery waits for the release gate.
- **Every release carries its proof.** One page bound to the exact diff by SHA-256: verdict, commands, policy, cost, risk and residual gaps.
- **No silent retry.** A blocked task stays blocked until a person changes the plan or the evidence.

Mira, the magpie courier, appears in the empty state and at the current milestone — never as a chat avatar and never instead of status text. Brand notes: [`docs/brand/mascot.md`](docs/brand/mascot.md).

## How it works

```text
signal → reproduce → plan gate → build → check · challenge · prove → release gate → return
```

| Step | What happens |
|---|---|
| **Signal** | A person, a tracker or a detector reports the problem. |
| **Reproduce** | A failing test or scenario runs against the base commit. |
| **Plan gate** | A person approves the scenarios that will judge the change. |
| **Build** | `openjiuwen` edits a disposable git worktree; policy checks every touched path. |
| **Check** | Repository tests, an independent challenger, then P0/P1 scenarios. |
| **Prove** | The evidence page is computed from the run and bound to the diff. |
| **Release gate** | A person approves the exact commit; release and publishing are the next milestone. |
| **Return** | The proof is shaped to return to the app, tracker or person that reported it. |

Verdict rule: **all P0 pass and P1 pass rate ≥ 80%**. Anything else blocks. A blocked task is terminal until a person acts.

## See it in 60 seconds

```bash
uv sync --extra dev
python scripts/demo-ui.py
# use the path printed by the script
uv run works --home /path/printed/by/demo ui
```

The demo is local, deterministic and free: no model, no network, no external services. It creates five tasks on products people know — Firefox, LibreOffice, GIMP, Blender and Joplin — including a blocked tablet-zoom check and a task in the middle of **Checked**.

Report from the GUI (opt-in writes, queued only):

```bash
uv run works --home /path/printed/by/demo ui --write
```

The `+ Report a bug` button creates a queued task. It never starts a run and never approves a gate.

The original recorded M0 demo:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/demo-m0.ps1
```

## Use it on a real repository

Readiness is a gate, not a warning. Add `.works/readiness.yaml` and a feature map first; a live run refuses to start while the gate is red.

```bash
uv sync --extra live
# openjiuwen must be installed or on PYTHONPATH; see docs/live-harness.md
uv run works readiness --repo /path/to/repo
uv run works source github owner/name --product MyProduct --label bug
uv run works source detector --file alerts.json --product MyProduct
uv run works submit --repo /path/to/repo --product MyProduct --ref GH-42 --title "The export drops the last column"
uv run works run <task-id> --live --approve-plan --scenarios scenarios.yaml
uv run works run <task-id> --live --verifier docker --scenarios scenarios.yaml
uv run works release <task-id>
uv run works approve <task-id> --gate release
uv run works deliver <task-id> --provider github
uv run works confirm <task-id> --url https://app.example/health --provider github --close
uv run works team verify <task-id>
uv run works swarm doctor
```

A product can point at its checkout once in `.works/products.yaml`, so `--product MyProduct` is
enough; see [`docs/intake.md`](docs/intake.md).

The live builder needs `ANTHROPIC_API_KEY` (or `WORKS_MODEL_KEY`). PPMA memory is optional:

```bash
uv run works run <task-id> --live --ppma http://127.0.0.1:8766
uv run works memory backfill --ppma http://127.0.0.1:8766
uv run works memory recall --ppma http://127.0.0.1:8766
```

## What works today

| Area | State |
|---|---|
| **Loop** | Queue, policy, disposable worktree, reproduce, build, check, proof and ledger work end to end. |
| **Live builder** | Real `openjiuwen` Claude Code harness on an Anthropic-compatible endpoint; model, tokens, USD and prompt hash are recorded. |
| **Proof** | Computed evidence page and immutable ledger row; P0/P1 verdict, policy, risk, cost, diff and residual gaps. |
| **GUI** | Story is the default human reading; Evidence is one click away; a Release view carries the packet, delivery, confirmation and team verdict; a Thread worklog adds a model-backed, streamed `Ask Mira` that is advisory only. Inline artifacts, product map, detectors, intake and a new-task form. |
| **Readiness** | `works readiness` runs lint, format, types, fast tests, product verify, architecture and import boundaries; the report carries the internal import graph and fails on cycles, and a red gate blocks live runs. |
| **Feature map** | `features/<product>.yaml`; Evidence shows covered, failed and not-covered features. |
| **Memory** | When configured, finished runs are reported to PPMA; older runs can be backfilled; `works memory recall` reads statements. |
| **Decision layer** | `DecisionPort` and `LaixGate` exist behind a deterministic fallback; off by default, shadow opt-in. |
| **Agent-core team** | `works team verify` runs inspector + challenger + reporter on `BaseTeam`/`TeamRuntime`; model-free, no API key. |
| **Ask Mira** | The Thread view can ask a real `openjiuwen` model about the recorded run; answers stream into the worklog and are advisory, never a gate. |
| **Intake** | GitHub Issues, Jira and firing detector alerts become queued tasks with `(kind, ref)` deduplication; `.works/products.yaml` maps a product to its checkout. |
| **Verifier container** | `--verifier docker` runs checks with no network, dropped capabilities and only the worktree mounted; a missing daemon is an error, never a silent host fallback. |
| **Provider split** | The verifier environment drops builder credentials, `works doctor` warns when both roles share one key, and the proof records the verifier and its isolation. |
| **JiuwenSwarm boundary** | `works run --swarm` speaks `works.swarm.v1` to an isolated entrypoint; `works swarm doctor` reports why the local checkout cannot start yet. |
| **Release gate** | `works approve --gate release` binds gate 2 to the base commit and proof, moves the task to `released`, and records `release.json`; a repeat is idempotent. |
| **Delivery** | `works deliver` commits the approved diff with `Works-Run:` trailers, pushes `works/<task-id>`, opens one GitHub PR or GitLab MR, and returns one comment to GitHub, GitLab or Jira. |
| **Confirmation** | `works confirm` re-checks the delivered commit (HTTP, command or the plan's scenarios) and returns to the tracker, optionally closing a GitHub/GitLab issue or moving a Jira issue to Done. |

## Roadmap

Three things turn the preview into the full factory:

- **Independent verifier.** The container boundary exists; the remaining work is the provider split and a live daemon in CI.
- **Release and return.** Gate 2, delivery and confirmation exist; a live pull request, comment and
  issue close need a real remote and `GITHUB_TOKEN`.
- **Depth in memory and evidence.** Feed PPMA recall into the planner, attach runtime artifacts, and execute feature selectors in the preview.

LAIX is optional and keeps the deterministic gate as the fallback. Merging stays human.

## Engineering standard

Python 3.12, strict `mypy`, `ruff`, `pydantic`, `hypothesis`, mutation testing on state/policy/queue, versioned prompts, schema migrations, structured JSON logs and supply-chain checks.

```bash
make check          # ruff, format, mypy, pytest with coverage
make integration    # the whole loop, no model
make bench          # CLI, status and evidence budgets
```

CI runs lint, tests, bandit and gitleaks; mutation and `pip-audit` run weekly. Decisions are recorded as ADRs in [`docs/adrs/`](docs/adrs/), and known failures are in [`docs/runbook.md`](docs/runbook.md).

## Documentation

| Document | What it answers |
|---|---|
| [`docs/plan.md`](docs/plan.md) | Milestones, checkboxes, standards and refactoring gates |
| [`docs/ui.md`](docs/ui.md) | Story, Evidence, report intake and the read-only/write boundary |
| [`docs/release.md`](docs/release.md) | Release packet, gate 2, delivery and confirmation |
| [`docs/readiness.md`](docs/readiness.md) | `.works/readiness.yaml` and the autonomy gate |
| [`docs/features.md`](docs/features.md) | Feature map format and proof coverage |
| [`docs/live-harness.md`](docs/live-harness.md) | Real `openjiuwen` builder setup |
| [`docs/agent-core.md`](docs/agent-core.md) | agent-core harness, verification team and Ask Mira |
| [`docs/intake.md`](docs/intake.md) | GitHub/Jira/detector intake and product-to-repository map |
| [`docs/swarm.md`](docs/swarm.md) | Isolated JiuwenSwarm builder contract |
| [`docs/ppma.md`](docs/ppma.md) | PPMA north contract, backfill and recall |
| [`docs/laix.md`](docs/laix.md) | Decision-layer boundary and rollout |
| [`docs/verification.md`](docs/verification.md) | Verification and approval boundaries |
| [`docs/waiting-and-dispatch.md`](docs/waiting-and-dispatch.md) | Waits, wake events and dispatch |
| [`docs/adrs/`](docs/adrs/) | Fifteen architecture decisions |

## Repository map

```text
src/works/          engine: queue, state, policy, flow, supervisor, evidence
src/works/ui/       local Story/Evidence preview
flows/              the fix-issue flow as a node graph
fixtures/           planted-bug repo, scenarios, traces and decision cases
tests/              unit, property, CLI, integration and golden proof tests
docs/               plan, ADRs, UI, readiness, memory and brand
scripts/            demo, benchmark, checks, deck and film
```

## License

Apache-2.0. See [`LICENSE`](LICENSE).
