# Local GUI

`works ui` starts the FastAPI app and opens a local window over the queue and run artifacts. It is
read-only by default; `works ui --write` enables task creation, intake, readiness, release, delivery,
confirmation and team verification. For a headless process use `works daemon start --write` and
`works daemon stop|status`; both print the bootstrap URL for the browser.

```powershell
works --home C:\path\to\workspace ui --port 8765
works --home C:\path\to\workspace ui --port 8765 --write
works --home C:\path\to\workspace daemon start --write --port 8765
works --home C:\path\to\workspace daemon status
works --home C:\path\to\workspace daemon stop
# open the printed URL; Ctrl+C stops a foreground ui
```

Global `--home` comes before the subcommand. Use `--no-open` to avoid launching a browser.

## React/Vite and live updates

The interface is a React/Vite app in `web/`; `works ui` serves its built assets from
`src/works/interfaces/ui/static/dist`. The queue and open task subscribe to `GET /api/v1/events` (SSE), so a
new run, event, gate, note or answer appears without a reload; the Settings fallback refresh is
used only if the stream drops. `Ask Mira` keeps its own `POST /api/v1/ask/stream` token stream.

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
  tracker comment), deployment status when recorded, confirmation (pass/fail, target, output SHA),
  team verdict, verifier isolation, LAIX shadow and run history with a two-run comparison. In
  `--write`, the same view can release, deliver, confirm and verify.
- **Session** (the Thread worklog, deep link `/thread`): the whole run reads as one
  **conversation**. It opens with the person's report on the right, then the pipeline continues on
  the left — reproduction, plan, build, check and release — with a quiet phase divider before each
  stage. Question cards appear inline (plan and release) and carry their own human actions; a plan
  gate or a blocked run adds one decision card above the thread, while a release card stays inline.
  Agent commentary and discussion collapse into one **Review** block; gate, challenge and hash rows
  sit behind **Details**. The header carries two views — **Conversation** and **Run log** — and a
  separate **Ask AI** group; **Review** and **Commentary** add labelled model output (with a busy
  state and a toast) and return to Conversation, so they never look like extra views. The rail stays
  at the right edge of the session: Decision, human Activity, Run, People and Technical. The
  conversation measure is 900px inside the full pane; the app bar, title and tabs stay on the shared
  content frame. **Run log** keeps the same column and header, and adds a compact chapter bar
  (Plan / Build / Check / Release) with event counts; the current chapter opens, the **All
  chapters** checkbox expands everything, and **Back to current** returns. In `--write`, `Add
  context` appends a
  `thread.note`; `Ask Mira` asks a real `openjiuwen` model and streams the answer into `thread.agent`. Follow-up questions
  carry the last three recorded answers. Every model answer is labelled and advisory: it cannot
  approve, release, retry or change a gate. `Review` adds a labelled Inspector / Challenger /
  Reporter discussion; `Commentary` adds Builder / Inspector / Reporter notes. Both are model output
  and cannot open a gate.
- **Factory**: a header action opens metrics and the ledger. The Release view carries the run history
  and a two-run comparison; Evidence offers proof/run/release/delivery/confirmation downloads.
  Artifacts open in a lightbox; a before/after pair has a drag slider; timeline rows open their raw
  event. **Settings → Builder** has two levels, so the two Jiuwen paths cannot be mistaken for
  interchangeable providers: first the runtime (**OpenJiuwen harness**, one agent inside Works, or
  **JiuwenSwarm**, a multi-agent team outside Works), then — only for OpenJiuwen — the provider
  (Claude Code, DeepSeek Harness, Jiuwen native or Codex). The runtime cards carry `inside Works` /
  `outside Works` badges and a one-line comparison, and availability and credential status are
  shown in provider terms, never as environment variable names. Keys stay in the local environment.
  The same panel selects a separate verifier provider for OpenJiuwen, optional models, theme,
  density, polling and the default repository. JiuwenSwarm is shown as a separate team with its own
  adapter and challenger, not as a provider card. **Settings → Planner** selects the plan mode
  (deterministic, shadow, assisted or deep), the read-only planner provider/model and the deep-mode
  critic; the plan is versioned, linted and approved by hash on the plan gate.

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
bar, a 280px queue, one shared content frame (app bar, title, status and tabs), a pipeline
conversation with a 900px measure and a right-edge context rail, a Run log chapter bar in the same
column, and inline human gates. One coral accent, subtle depth
instead of stacked borders, visible focus, text labels for every status, `prefers-reduced-motion`,
and Mira in the empty state. Below 720 px the route becomes
a vertical list with the same states and per-milestone screen-reader names; the queue moves below
the Story so the task is visible first. Replay updates the route and receipt in place.
`Ctrl K` opens a command palette; `/` focuses search; `j`/`k` move through the queue; `t` toggles
the theme; `c` toggles Present mode; `?` shows the keyboard help.

Times have one source: the hero, the header and the route all read the reported time from the same
`task.created` event, so the page cannot show two different “Reported” moments.

## Read-only by default, writes on request

The server binds to `127.0.0.1` and reads are open on loopback. A write in the default mode returns
`403 read_only`; reads never write `queue/` or `runs/`.

`works ui --write` opens the first write path: a **+ New task** button in the task list context.
It opens a Claude-style prompt ("What should Mira work on?") with the exact fields under
**Details**. The typed text is parsed locally for a reference, product, repository and title;
untouched fields follow the draft and stop following it when a person edits one. No model is
called and nothing is created by itself. It creates only a `queued`
task through `POST /api/v1/tasks` (bearer or session auth, repo/.git, reference and title
validation), never starts a run and never approves a gate. The same mode lets
the Evidence readiness panel run `works readiness` through a local POST.

## Limits

- Readiness commands run only in `--write`; the default preview shows static checks.
- Live updates use `GET /api/v1/events` (SSE); the Settings fallback refresh is configurable.
- Writes need the persistent bearer token from `.works/state/http-token` or the one-time bootstrap
  URL; reads are open on loopback. Do not bind the UI to a non-loopback address. A LAN/phone client
  needs the authenticated remote daemon described in `docs/guides/remote.md`.
- React 19 + Vite, built into `src/works/interfaces/ui/static/dist`; no Tailwind or shadcn yet. The
  Playwright journeys run in CI against a seeded daemon on port 8791.

Tests: `pytest tests/unit/interfaces/api tests/contract` for the API and parity fixtures;
`cd web && npm test` for the screen matrix. The daemon lifecycle gate is
`python scripts/smoke_daemon.py`.

Two journeys need a secret and are therefore opt-in, not required checks:

```bash
cd web
WORKS_E2E_GITHUB=1 npx playwright test e2e/opt-in.spec.ts -g "GitHub issue"   # gh auth token
WORKS_E2E_ASK=1    npx playwright test e2e/opt-in.spec.ts -g "streams"       # model key
```

The first imports an open issue from `WORKS_E2E_GITHUB_REPO` (default
`michaelatamuk/works-calc-demo`) and asserts a tracker task appeared. The second asks a question over
`POST /api/v1/ask/stream` and asserts the SSE stream ends with a `done` event and no `error`.
