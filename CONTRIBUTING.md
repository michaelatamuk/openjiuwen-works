# Contributing

Small, typed, tested changes. [Status](docs/roadmap/status.md) records what is left; the bar is the
[engineering standard](docs/guides/contributing/engineering-standard.md).

## Setup

```bash
uv sync --extra dev
uv run works --help
uv run pre-commit install
```

`uv sync` makes the venv match `uv.lock` for the extras you name, and removes anything else as
extraneous. If you also want the live providers, name them in the same command:

```bash
uv sync --extra dev --extra server --extra providers   # native + dsh + codex + claude
```

Do not mix `pip install` with `uv sync` in the same environment: the next sync treats pip-installed
packages as extraneous and removes them.

## Before a PR

```bash
make check          # ruff, format, mypy, pytest with coverage, docs structure
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

## Documentation

- A new page goes in the directory that matches the reader's question, not the author's. The
  placement table, manifest fields and status rules are in
  [`docs/guides/contributing/docs.md`](docs/guides/contributing/docs.md).
- Every page under `docs/` is registered in `docs/manifest.yaml`; ADRs are indexed in
  `docs/adrs/README.md`, and `docs/archive/` is read-only. `make docs` checks all of it.
- A non-active page carries a status banner under its H1, and the banner must agree with the
  manifest. Do not hand-edit `docs/reference/generated/`.

## Typed frontend

- Every component is `.tsx` with an explicit exported props type; `allowJs` is off. Import helpers
  without an extension and keep per-feature domain types in `types.ts`.
- No `any`, `as any`, `@ts-ignore` or `@ts-expect-error` in `src/app|features|ui|api`. CI greps for
  them; raw JSON fixtures in `src/test` are the only allowed cast boundary.
- Narrow a loose API payload once, at the boundary (`appDetail`, `queueTask`, `appBuilder`), never
  inside a component.
- The HTTP boundary is validated with Zod in `src/api/schemas.ts`. Keep the contracts minimal
  (identity + state, plus the fields the screens require); a mismatch is an `ApiError` with
  `bad_response` and a named field, not a blank screen.
- Before a PR: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, `npm run e2e`.

## Async boundary and renderer

- Every HTTP operation has a class in `src/works/interfaces/api/route_classes.py`; `make routes`
  checks it and the table in `docs/reference/platform/http-api.md`. Blocking handlers stay `def` and run in
  FastAPI's thread pool; do not rewrite a git or subprocess route as `async def` for style.
- Jobs run on one bounded executor owned by `JobRunner` (ADR 019). Do not start an anonymous thread;
  the queue bound and the shutdown path depend on that single owner.
- The frontend is a client-side SPA. React Server Components, Next.js and Server Actions are
  deliberately rejected (ADR 020); streaming is SSE from the daemon.

## Reporting a bug in Works itself

Open an issue with the task id, the run id, the stop reason and the proof page. That is exactly the
evidence the engine produces, so a bug report and a run record are the same shape.
