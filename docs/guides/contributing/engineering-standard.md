# Engineering standard

> **Doc status:** active · **Owner:** Michael · **Last reviewed:** 2026-11-27

Every commit satisfies this. It is checked in CI, not in review comments. This is the bar referenced
by [`CONTRIBUTING.md`](../../../CONTRIBUTING.md); the original v4.24 plan is archived at
[`docs/roadmap/archive/plan-v4.md`](../../roadmap/archive/plan-v4.md).

**Language and shape**

- Python **3.12**, `from __future__ import annotations`, type hints on every public function.
- `mypy --strict` on `src/`; no `Any` without a one-line reason; no `# type: ignore` without a code.
- `ruff` for lint and format; no warnings, no unused imports, no dead code.
- Async for I/O; `asyncio.TaskGroup` for structured concurrency; no bare threads.
- Pure functions where possible; side effects at the edges; dependencies injected, not imported globally.
- One module, one reason to change. Domain types never import infrastructure.
- Errors: a typed exception hierarchy per component; `except Exception` only to log, add context and
  re-raise or convert into a stop reason.
- Structured JSON logs with `run_id`, `task_id`, `step`; no `print`.
- Config via pydantic settings; secret names documented; secrets never in files or prompts.
- Every persisted record carries `schema_version`; a migration function per bump.

**Tooling**

`uv` (env, lock) · `ruff` · `mypy` · `pytest` · `hypothesis` · `mutmut` · `bandit` · `pip-audit` ·
`gitleaks` · `pre-commit` · `cyclonedx` SBOM on release.

**Testing**

- Property-based tests for the state machine and path policy (adversarial paths, `..`, unicode).
- Contract tests for the harness adapter against recorded traces.
- Golden-file tests for evidence rendering; a change to the page is a reviewed diff.
- Mutation score ≥ 70% on `queue/`, `policy/`, `verify/`.
- Load test: 10 000 tasks in the queue, `status` still under 100 ms.

**Budgets**

- CLI cold start < 300 ms; `status` command logic < 100 ms (process startup excluded);
  evidence render < 1 s. Measured on the development host by `scripts/bench.py`: 206 ms, 59 ms at
  10 000 tasks, 0.02 ms.
- No dependency without a reason; a new dependency requires an ADR line.

**Every PR**

`make check` green (ruff, mypy, pytest), no new TODOs, docs updated, and if the change touches a
decision, an ADR is added or amended.

**Reliability**

- Every external call has a timeout, a bounded retry with jitter, and a typed failure.
- Circuit breaker around the model provider: after N consecutive failures, stop and say so; never
  loop on a dead provider.
- Idempotent everywhere it matters: submit, publish, comment, revert.
- Graceful degradation: if the verifier cannot run, the task blocks — it never "passes by default".

**Reproducibility**

- `uv.lock` committed; exact versions pinned; model id and version recorded per run.
- Fixed seeds in tests; recorded traces replayed in CI, not live model calls.
- `works schema` prints every persisted schema; a migration is tested with old fixtures.

**Supply chain**

- Pinned dependency hashes; `pip-audit` and Dependabot/Renovate weekly; `cyclonedx` SBOM per release.
- `gitleaks` on every push; signed commits from v0.2 onward.
- No dependency added without a reason in the PR and a line in the ADR.

**AI-specific quality**

- Prompts are versioned files with a hash; a prompt change requires a benchmark run before adoption.
- Every agent output that drives a decision is JSON validated by a schema — never parsed free text.
- The verifier runs at temperature 0 where the provider allows it, and the setting is recorded.
- Cost per step is captured from harness events and attributed to the run budget.
- Injection guard: issue text is fenced as data; the policy engine, not the model, enforces paths.
- A prompt change and a model change are never shipped in the same commit.
- Findings that drive a decision are structured records with evidence refs; free-form prose is
  never parsed into one.
- No agent grades its own work: challengers and verifiers are separate sessions and, where
  possible, separate providers.
- Every prompt is a versioned file with a hash; the hash is recorded in the run and the proof.

**Observability**

- Structured events carry `run_id`, `task_id`, `step`, `duration_ms`, `tokens`, `usd`.
- `works trace <run>` renders the timeline from events; nothing is reconstructed from logs.
- OpenTelemetry spans are optional in v0 but the event schema is ready for them.

**Process**

- Trunk-based, small PRs (< 400 changed lines), conventional commits, PR template asks for evidence.
- `CHANGELOG.md` per release; [`docs/guides/operations/runbook.md`](../operations/runbook.md) for
  known failures and their first response.
- Renovate weekly; a dependency update that breaks a test is fixed or reverted the same day.

## Related

- [Layout](layout.md) — where a module, route or screen belongs.
- [Typing](typing.md) — the `Any` ratchet and how to change it.
- [Docs](docs.md) — where a page belongs and how the manifest works.
- [Contributing](../../../CONTRIBUTING.md) — setup, rules and the PR checklist.
