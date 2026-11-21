# openJiuwen Works

A software factory: one signal goes in, a released fix comes out — and the fix goes back to
where the bug was seen.

**Status: M0.5 + live builder path.** The queue, policy, supervisor, evidence, ledger and CLI work
end to end. The builder can be the real `openjiuwen` Claude Code harness on the DeepSeek
Anthropic-compatible endpoint, and finished runs are reported to PPMA memory. The verifier is
still the local scenario runner (M2); nothing is published yet (M3).

<img src="brand/mascot/mira-primary.png" width="120" align="right" alt="Mira, a magpie courier, carrying a proof page">

Mira is the product's mascot: a magpie courier who carries the signal in and the proof back. Brand
notes and poses are in [`docs/brand/mascot.md`](docs/brand/mascot.md).

---

## The idea

Today a bug spends days in queues: for triage, for an agent's answers, for a reviewer's time,
for someone to prove the change works. Writing the code is the short part.

openJiuwen Works moves the waiting into an engine. It takes a signal from three places — a
failure caught by DigitalMate, a bug already filed in a tracker, a person reporting it — and
carries it through ten steps. People appear at exactly two gates: the plan and the release.

What comes back is not a diff to read. It is one page: what changed, what was tested, what it
cost. Then the fix ships to the app, the tracker or the person who reported it, and the report
closes.

---

## Try it

```bash
uv sync --extra dev
uv run works --help
```

The live builder is opt-in: `uv sync --extra live` and an installed (or `PYTHONPATH`-visible)
`openjiuwen`; see `docs/live-harness.md`.

The full M0 demo, with a planted bug and a recorded proposal:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/demo-m0.ps1
```

It submits a task, shows a dry run, refuses a test edit, runs the loop, and prints the proof and
the ledger row. No model and no network are used.

---

## What works today

| Command | What it does |
|---|---|
| `works submit --ref GH-42 --repo .` | Creates a task; the same `(kind, ref)` returns the same task |
| `works status [task]` | Lists the queue from a derived index; one task with owner and event count |
| `works task <task>` | Prints the projection and verifies it against a full replay |
| `works trace <task>` | Renders the timeline from the event store |
| `works approve <task>` | Closes the plan gate |
| `works run <task> --dry-run` | Shows nodes and scenarios; changes nothing |
| `works run <task> --scenarios … --trace …` | Reproduce → plan → build → test → scenarios → proof (recorded) |
| `works run <task> --live …` | The same loop with the real `openjiuwen` Claude Code harness |
| `works run <task> --ppma URL` | Report the finished run to PPMA memory over its north contract |
| `works wait <task> --on review` | Wait for a review/CI/deploy event instead of blocking |
| `works wake <task> --event …` | Wake a waiting task and advance to its next state |
| `works dispatch` | Claim and run ready tasks; `--watch` keeps the loop alive |
| `works policy check <paths>` | Refuses test paths and escapes before any command runs |
| `works finding add/list <task>` | Structured findings with confidence and uncertainty |
| `works metrics` | Attention, waiting time and cost derived from events and the ledger |
| `works ledger` | Reads the append-only ledger |
| `works schema --json` | Prints every persisted JSON Schema and its version |
| `works doctor` | Checks Python, git, workspace, flow, harness, container, credentials, isolation |

Every command takes `--json` and returns a stable exit code: `0` ok, `2` usage, `3` policy,
`4` state, `5` not found, `6` config, `7` conflict, `8` blocked, `1` internal.

### The loop

1. **Reproduce** — a deterministic command must fail on the base commit.
2. **Plan** — the scenario ids that will judge the change; gate 1 is a person.
3. **Build** — a bounded harness port returns a unified diff. Policy checks every touched path
   *before* the patch is applied.
4. **Check** — the repository's own tests, then an independent challenger session that tries to
   disprove the change, then the P0/P1 scenarios in a separate directory.
5. **Prove** — a computed page bound to the diff by SHA-256: verdict, commands, policy, cost, diff.
6. **Ledger** — one append-only row per finished run.

Verdict rule: all P0 pass and P1 pass rate ≥ 80%; anything else blocks. A blocked task is terminal
in v0 — no silent retry, no "trust the builder".

---

## What is not real yet

| Area | State |
|---|---|
| Live harness | Works: `openjiuwen` + bundled `claude.exe` + DeepSeek Anthropic endpoint; measured 115.6 s / 104 563 tokens / $0.094 for the fixture fix |
| Verifier | The local scenario runner stands in; the container and provider split land in M2 |
| Release | The loop stops at `proved`; branch, PR and the issue comment land in M3 |
| Memory | Finished runs are posted to PPMA (`works.run_finished`); recall and lessons are M4 |
| GUI | CLI only. The 2026 window standard is in the plan, §6.5, for after M2 |

The fixture bug is deliberate: `add` subtracts. The good trace fixes it, the sneaky trace passes
the visible test but fails a P0 holdout, and the test-edit trace is refused by policy.

---

## Engineering standard

The plan carries a 2026 engineering standard (§6.4): Python 3.12, mypy strict, ruff, uv, pydantic,
hypothesis, mutation testing ≥ 70% on `state/`, `policy/` and `queue/`, structured JSON logs,
schema versions and migrations, pinned models and prompts, supply-chain checks (bandit, pip-audit,
gitleaks), and scheduled refactoring gates RG0–RG4 (§6.6).

Measured budgets (`python scripts/bench.py`):

| Budget | Measured | Target |
|---|---|---|
| CLI start | 206 ms | < 300 ms |
| `status` logic, 10 000 tasks | 59 ms | < 100 ms |
| Evidence render | 0.02 ms | < 1 s |

Checks:

```bash
make check          # ruff, ruff format --check, mypy, pytest with coverage
make integration    # the whole loop, no model
make bench          # re-measure the budgets
```

CI adds bandit and gitleaks on every PR, a weekly mutation gate (71.8% on state, policy and queue),
and a weekly `pip-audit`. Decisions are recorded as ADRs in `docs/adrs/`; known failures and first
responses are in `docs/runbook.md`. The live builder is in `docs/live-harness.md`; the PPMA memory
integration is in `docs/ppma.md`; the factory comparison that shaped v4.5 is in
`docs/review-4-factories.md`; waits and the dispatcher are in `docs/waiting-and-dispatch.md`.

---

## Layout

| Path | What it is |
|---|---|
| `src/works/` | The engine: state, queue, index, policy, flow, supervisor, evidence, harness port |
| `tests/` | Unit, property-based, CLI and integration tests; golden evidence page |
| `fixtures/` | A planted-bug repository, three scenarios and four recorded traces |
| `flows/fix-issue.yaml` | The first flow as a node graph with gates and policy |
| `docs/plan.md` | The plan: preconditions, milestones, checkboxes, standards, refactoring gates |
| `docs/deck/` | Five slides (SVG + PNG) |
| `docs/video/` | The 47 s concept film |
| `docs/adrs/` | Ten architecture decisions |
| `scripts/` | Demo, benchmark, check, mutation gate, film generators |

---

## Deck order

1. **The problem** — a customer in Berlin, the wrong VAT, four days of waiting.
2. **How it works** — ten steps, two gates, the products it uses.
3. **Why now** — the bottleneck moved; what a factory needs; flows and success metrics.
4. **Appendices** — the flow as a file, and as ten boxes.

## Design in one paragraph

A **window** and an **engine**. The window is where a person reports, watches and approves. The
engine owns the queue, the check and the proof. Everything else is a tool it calls: `jiuwenswarm`
builds in a worktree and runs CI, `agent-core` runs the checking agent in a clean context, `PPMA`
keeps the project state, `Orbit` optionally shares the proof with a team room. Nothing is forked;
every link is a published contract.

---

## Building the deck and the film

Requires Chrome, Python 3.11+ and ffmpeg.

```bash
python scripts/make_anim.py     # frames -> docs/frames
python scripts/make_audio.py    # ticks, dings and the pad
python scripts/build_anim.py    # docs/video/openjiuwen-works-two-mondays.mp4
```

Narration is generated with Windows SAPI (`scripts/anim_tts.ps1`). Swap in a real voice-over and
the edit stays the same.

## Numbers

Two only: **4 days** the usual way, **1 h 45 min** with Works. Both are illustrative and labelled
as such on the slides.

## License

Apache-2.0. See LICENSE.
