# Read-only preview

`works ui` opens a local, read-only window over the queue and run artifacts. It is the first
deliverable of the GUI path; the full window follows the 2026 standard in plan §6.5.

```powershell
works --home C:\path\to\workspace ui --port 8765
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
  scenarios, risk, decision, commands, diff, policy, residual risk and timeline.

There is no separate Summary tab: the human answer lives in the Story hero and the receipt strip.
Both views are computed from the same proof, so they cannot disagree. Deep links carry the view:
`#/task/<id>/story`, `#/task/<id>/evidence` and `#/task/<id>/story?at=5`.

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

## Read-only by construction

The server binds to `127.0.0.1` by default and only serves GET/HEAD. A POST returns `405` with a
plain explanation. It reads `queue/` and `runs/`; it never writes them.

## Limits

- Basic readiness, no feature map yet.
- Polling every 15 s, not SSE.
- No auth; local-only preview.
- Vanilla HTML/CSS/JS for the preview; the final window is React 19 + TypeScript + Vite + Tailwind +
  shadcn/ui, with Playwright and axe, per plan §6.5.

Tests: `pytest tests/test_ui.py tests/test_ui_pipeline.py`.
