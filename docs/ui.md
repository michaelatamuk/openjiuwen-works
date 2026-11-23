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

## React/Vite and live updates

The interface is a React/Vite app in `web/`; `works ui` serves its built assets from
`src/works/ui/static/dist`. The queue and open task subscribe to `GET /api/events` (SSE), so a
new run, event, gate, note or answer appears without a reload; the Settings fallback refresh is
used only if the stream drops. `Ask Mira` keeps its own `POST /api/ask/stream` token stream.

To rebuild after a UI change:

```bash
cd web
npm ci
npm run build
```

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
  LAIX shadow and run history with a two-run comparison. In `--write`, the same view can release,
  deliver, confirm and verify.
- **Session** (the Thread worklog, deep link `/thread`): a full-height pane inside the shared
  content frame. The task title, status and tabs are global and aligned with the pane. The pane
  starts with source + Live and one decision card, then a vertical **Chapters** outline
  (Plan / Build / Check / Release) with state and summary. Only the selected chapter opens; past
  work is a one-line summary in the outline, and **Full log** shows every chapter. Agent
  commentary and discussion collapse into one **Review** block. The conversation measure is 900px,
  while the pane uses the rest of the width for the outline and context rail. The composer is one
  row — `Ask`/`Note`, input, filled send — and suggested questions fill an empty conversation.
  The rail is a separate pane: Decision, human Activity, Run, People, and Technical. Old chapters
  and technical noise never compete with the current decision. In `--write`, `Add context` appends
  a `thread.note`; `Ask Mira` asks a real `openjiuwen` model and streams the answer into
  `thread.agent`. Follow-up questions carry the last three recorded answers. Every model answer is
  labelled and advisory: it cannot approve, release, retry or change a gate. `Review` adds a
  labelled Inspector / Challenger / Reporter discussion; `Commentary` adds Builder / Inspector /
  Reporter notes. Both are model output and cannot open a gate.
- **Factory**: a header action opens metrics and the ledger. The Release view carries the run history
  and a two-run comparison; Evidence offers proof/run/release/delivery/confirmation downloads.
  Artifacts open in a lightbox; a before/after pair has a drag slider; timeline rows open their raw
  event. Settings control theme, density, polling and the default repository.

There is no separate Summary tab: the human answer lives in the Story hero and the receipt strip.
Both views are computed from the same proof, so they cannot disagree. Deep links carry the view:
`#/task/<id>/story`, `#/task/<id>/evidence`, `#/task/<id>/release`, `#/task/<id>/thread` and `#/task/<id>/story?at=5`.

A blocked task explains the stop in place: the failed check, why it matters, what was not released
and who decides next. “See what failed” scrolls to that rail. The same rule holds in the hero: no
green badge and no “fixed” claim without a passing proof.

`C` toggles Present mode; `Esc` leaves it. `/` focuses search, `Ctrl K` opens the palette and `j`/`k` move through the queue. The preview opens with **no task selected**: the queue is
visible and Mira waits in the main empty state. Selecting a report opens its Story; the queue stays
visible on the left.

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

Dark and light themes, comfortable and compact density, a near-white surface system, a 52px app
bar, a 280px queue, one shared content frame, a 220px vertical chapter outline, a 900px conversation
measure and a 340px context pane. One coral accent, subtle depth instead of stacked borders, visible
focus, text labels for every status, `prefers-reduced-motion`, and Mira in the empty state. Below 720 px the route becomes
a vertical list with the same states and per-milestone screen-reader names; the queue moves below
the Story so the task is visible first. Replay updates the route and receipt in place.
`Ctrl K` opens a command palette; `/` focuses search; `j`/`k` move through the queue; `t` toggles
the theme; `c` toggles Present mode; `?` shows the keyboard help.

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
- Live updates use `GET /api/events` (SSE); the Settings fallback refresh is configurable.
- No auth; local-only writes. The LAN preview stays read-only.
- React 19 + Vite, built into `src/works/ui/static/dist`; no Tailwind or shadcn yet, and Playwright
  is not wired into CI.

Tests: `pytest tests/test_ui.py tests/test_ui_pipeline.py`.
