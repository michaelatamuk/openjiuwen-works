# Layout

The engine is layered top-down: `interfaces` call `application`, `application` calls `adapters` and
`domain`, and `domain` imports nothing from the layers above it. A module belongs in the layer whose
job it describes, not in the layer that happens to use it.

```
src/works/
  config/          paths, logging, sys.path hardening
  domain/          pure records, rules and rendering with no I/O
  application/     use cases: the supervisor, planning, execution, delivery, approvals, memory
  adapters/        the outside world: queue files, git, processes, harnesses
  interfaces/      CLI, HTTP API, built UI assets
web/src/
  app/             entry point, shell and hash routing
  features/        queue, session, story, evidence, release, settings, dialogs
  ui/              small primitives (Modal, Card, Table, Pill, Toast)
  lib/             API client and formatting helpers
  styles/          foundation, session and shell CSS passes
tests/
  unit/            mirrors src/works by layer
  integration/     whole-loop, Docker, Swarm, team and performance tests
```

## Adding things

- **CLI command:** the handler goes in `interfaces/cli/commands/<group>.py`; its arguments go in
  `interfaces/cli/parser/<group>.py`. Groups are `tasks`, `plan`, `run`, `delivery`, `intake`,
  `inspect`, `gates`, `quality`, `memory`, `team` and `ui`.
- **HTTP route:** GET payloads go in `interfaces/api/read.py`, POST routes in
  `interfaces/api/write.py`; both return `(HTTPStatus, payload)`. `server.py` only parses the
  envelope, dispatches and sends the response. Streaming and binary responses stay in the handler.
- **Thread message:** add a small handler in the lifecycle module under
  `interfaces/api/presenters/thread/messages/` (`signal`, `plan`, `build`, `verify`, `deliver`,
  `notes`) and register the event type in `core.py`.
- **Story stage:** labels and maps live in `interfaces/api/presenters/story/stages.py`; the pipeline
  assembly stays in `pipeline.py`.
- **Plan mode, gate or verifier:** planning lives in `application/planning/`, gates in
  `application/approvals/`, verification in `application/execution/`.
- **Run phase:** `application/supervisor/core.py` is the facade; the phases live in
  `application/supervisor/{planning,execution,verification,recording}.py` and take the supervisor
  explicitly.
- **A new persisted record:** the model goes in `domain/`, the store in `adapters/`, and
  `domain/records.py` re-exports it for callers that read a whole task or run.

## Rules of thumb

- `domain/` never imports `application/` or `adapters/`.
- A package with more than a screenful of unrelated concerns becomes a folder with one module per
  concern; the folder `__init__.py` keeps the public imports stable.
- Keep the deterministic path deterministic: recorded traces never call a model.
