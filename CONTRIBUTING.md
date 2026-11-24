# Contributing

Small, typed, tested changes. The plan is the source of truth for scope; the engineering standard
in `docs/design/plan.md` §6.4 is the bar.

## Setup

```bash
uv sync --extra dev
uv run works --help
uv run pre-commit install
```

## Before a PR

```bash
make check          # ruff, format, mypy, pytest with coverage
make integration    # the whole loop, no model
make bench          # budgets; do not regress without an ADR line
```

Or on Windows: `powershell -ExecutionPolicy Bypass -File scripts/check.ps1`.

## Rules

- Trunk-based; short-lived branches from `main`; one pull request per task.
- Conventional commits. A PR under 400 changed lines unless it is a rename or a deletion.
- Every public function is typed; `mypy --strict` covers `src/`.
- A new dependency needs a reason in the PR and a line in an ADR.
- A change to a decision needs a new ADR or an amendment; never edit history silently.
- Do not weaken the path policy to make a change fit. Narrow the change.
- If a change touches `web/`, Vitest parity tests are required today; Playwright/axe and
  opt-in visual snapshots become required when the E2E job lands (2026 plan, M3).
- No new TODO; an old TODO is a refactoring trigger at the next gate.
- Refactoring is scheduled (RG0–RG4). Do not mix it with feature work.

## Reporting a bug in Works itself

Open an issue with the task id, the run id, the stop reason and the proof page. That is exactly the
evidence the engine produces, so a bug report and a run record are the same shape.
