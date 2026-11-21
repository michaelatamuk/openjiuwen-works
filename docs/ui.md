# Read-only preview

`works ui` opens a local, read-only window over the queue and run artifacts. It is the first
deliverable of the GUI path; the full window follows the 2026 standard in plan §6.5.

```powershell
works --home C:\path\to\workspace ui --port 8765
# open the printed URL; Ctrl+C stops the server
```

Global `--home` comes before the subcommand. Use `--no-open` to avoid launching a browser.

## What it shows

- **Queue** — every task, state, source, product, flow, risk and decision; filter by waiting,
  blocked and proved; search; `j`/`k` navigation.
- **Proof** — verdict, scenario table, findings, challenge, commands, change and diff, policy,
  residual risk, cost and timeline.
- **Risk and decision** — level, reasons, owners, required reviewers, verb, reason code, confidence,
  approval and alternatives.
- **Readiness** — a basic preview (git, flow, project, tests, repository map); the full gate is
  T2.18.
- **Feature coverage** — a placeholder until the feature map lands with T2.19.

## Design and interaction

Dark and light themes, comfortable and compact density, one violet accent, borders instead of
decorative shadows, visible focus, text labels for every status, `prefers-reduced-motion`, and Mira
in the empty state. Deep links use `#/task/<id>`.

## Read-only by construction

The server binds to `127.0.0.1` by default and only serves GET/HEAD. A POST returns `405` with a
plain explanation. It reads `queue/` and `runs/`; it never writes them.

## Limits

- Basic readiness, no feature map yet.
- Polling every 15 s, not SSE.
- No auth; local-only preview.
- Vanilla HTML/CSS/JS for the preview; the final window is React 19 + TypeScript + Vite + Tailwind +
  shadcn/ui, with Playwright and axe, per plan §6.5.

Tests: `pytest tests/test_ui.py`.
