# Local GUI

`works ui` opens a local window over the queue and run artifacts. Read-only by default;
`works ui --write` enables task creation, intake, readiness, release, delivery, confirmation and
team verification.

```powershell
works --home C:\path\to\workspace ui --port 8765
works --home C:\path\to\workspace ui --port 8765 --write
# open the printed URL; Ctrl+C stops the server
```

Global `--home` comes before the subcommand. Use `--no-open` to avoid launching a browser.

## Two readings, one proof

The same evidence page serves two audiences without a second data source:

- **Story** (default): the road of one fix. A gray **Reported** origin (the signal, not part of
  Mira's journey) is followed by five Mira stops: **Picked up → Confirmed → Fixed → Checked →
  Delivered**. Each stop has four states: not started (dimmed), Mira is here (violet, in the middle
  of the work), done (green), or stopped (red); the release gate adds an amber **waits for you**
  state. The active stop reads as a sentence (“Mira is fixing it”, “Mira is checking it”, “Mira is
  ready to release”); future stops never get a Mira. The receipt
  strip answers what changed, what was checked, what was not, and who decides. “How we got here”
  keeps the replay out of the headline. The hero also states the recorded memory status —
  “PPMA synced”, “PPMA failed” or “Not recorded” — so the preview never fakes a green memory badge.
- **Evidence**: the answer for an engineer — the ten-step technical line, run metadata, verdict and
  scenarios, risk, decision, commands, diff, policy, residual risk, verifier, team, inline artifacts
  and a filtered timeline.
- **Release**: the operational answer — packet and blockers, gate 2, delivery (branch, commit, PR/MR,
  tracker comment), confirmation (pass/fail, target, output SHA), team verdict, verifier isolation,
  LAIX shadow, product map and detector alerts. In `--write`, the same view can release, deliver,
  confirm and verify.
- **Thread**: the worklog. Real events become role-labelled messages (Person, Builder, Verifier,
  Challenger, Team, Delivery, Confirmation, Mira) with structured cards and a right rail for task,
  factory, people, agents, deliverables, checks, cost and artifacts. In `--write` it has two inputs:
  **Add context** appends a `thread.note`; **Ask Mira** asks a real `openjiuwen` model about the
  recorded run. The answer streams token-by-token, is stored as `thread.agent`, and is advisory:
  it cannot approve, release, retry or change anything. Follow-up questions carry the last three
  recorded answers as history. Every model answer carries an `AI answer` badge; commentary and
  discussion carry their own labels. Inline plan/release questions carry
  recommended actions and `Open run`; `Generate commentary` adds labelled Builder / Inspector /
  Reporter messages, and `Team discussion` adds labelled Inspector / Challenger / Reporter
  messages with a stance. Both are model output: they are advisory and cannot open a gate.
- **Factory**: a header action opens metrics and the ledger. The Release view carries the run history
  and a two-run comparison; Evidence offers proof/run/release/delivery/confirmation downloads.
  Artifacts open in a lightbox; a before/after pair has a drag slider; timeline rows open their raw
  event. Settings control theme, density, polling and the default repository.

There is no separate Summary tab: the human answer lives in the Story hero and the receipt strip.
Both views are computed from the same proof, so they cannot disagree. Deep links carry the view:
`#/task/<id>/story`, `#/task/<id>/evidence`, `#/task/<id>/release` and `#/task/<id>/story?at=5`.

A blocked task explains the stop in place: the failed check, why it matters, what was not released
and who decides next. “See what failed” scrolls to that rail. The same rule holds in the hero: no
green badge and no “fixed” claim without a passing proof.

`C` toggles Present mode; `Esc` leaves it. The preview opens with **no task selected**: the queue is
visible and Mira waits in the main empty state. Selecting a report opens its Story; the breadcrumb
returns to the queue.

## Demo data

```powershell
python scripts/demo-ui.py
works --home "$env:TEMP\opencode\works-ui-demo-v6" ui
```

The demo has five tasks on open-source products people actually use — **Firefox, LibreOffice, GIMP,
Blender and Joplin** — with human issue titles and event times spread over hours. The GIMP task is
blocked by a tablet-zoom check, so the Story shows a plain-language stop. The Blender task is in the
middle of the check: the fix is done, Mira is checking it, Checked is the active stop and Delivered
is still dimmed. That makes it the task to screenshot when the story needs to show work in progress
without a failure or a finished run. The runs are local fixtures, not upstream fixes.

## What it shows

- **Queue** — grouped into **Needs you**, **In progress**, **Queued** and **Done**; filter, search
  and `j`/`k` navigation.
- **Story** — one sentence per task, the reported origin with five Mira stops, the four stop states,
  Mira at the current stop, the receipt strip, the recorded memory status, a specific blocked rail
  when stopped, and replay behind “How we got here”.
- **Evidence** — the ten-step technical line, run metadata (task/run id, base commit, rules version,
  evidence fingerprint, model, provider), verdict, findings, challenge, commands, change/diff,
  policy, risk, decision, readiness, feature map, residual risk, cost and timeline.
- **Readiness** — a basic preview (git, flow, project, tests, repository map); the full gate is
  T2.18.
- **Feature coverage** — every declared feature is shown as covered, failed or not covered by the
  proof's scenarios; runtime artifacts and selector checks are the remaining T2.19 work.

## Design and interaction

Dark and light themes, comfortable and compact density, one violet accent, borders instead of
decorative gradients, visible focus, text labels for every status, `prefers-reduced-motion`, and
Mira in the empty state. Below 720 px the route becomes a vertical list with the same states and
per-milestone screen-reader names; the queue moves below the Story so the task is visible first.
Replay updates the route and receipt in place. `Ctrl+K` opens a command palette; `/` focuses search;
`t` toggles the theme; `c` toggles Present mode; `?` shows the keyboard help.

Times have one source: the hero, the header and the route all read the reported time from the same
`task.created` event, so the page cannot show two different “Reported” moments.

## Read-only by default, writes on request

The server binds to `127.0.0.1` and serves GET/HEAD. A POST returns `405` in the default mode; it
reads `queue/` and `runs/` and never writes them.

`works ui --write` opens the first write path: a **+ New task** button in the task list context.
It opens a Claude-style prompt ("What should Mira work on?") with the exact fields under
**Details**. The typed text is parsed locally for a reference, product, repository and title;
untouched fields follow the draft and stop following it when a person edits one. No model is
called and nothing is created by itself. It creates only a `queued`
task through `POST /api/tasks` (local-only, `X-Works-Write`, repo/.git, reference and title
validation), never starts a run and never approves a gate. The same mode lets
the Evidence readiness panel run `works readiness` through a local POST.

## Limits

- Readiness commands run only in `--write`; the default preview shows static checks.
- Polling every 15 s, not SSE.
- No auth; local-only preview.
- Vanilla HTML/CSS/JS for the preview; the final window is React 19 + TypeScript + Vite + Tailwind +
  shadcn/ui, with Playwright and axe, per plan §6.5.

Tests: `pytest tests/test_ui.py tests/test_ui_pipeline.py`.
