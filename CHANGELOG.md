# Changelog

All notable changes are recorded here. The format follows Keep a Changelog, versions follow
Semantic Versioning.

## [0.0.1] — 2026-11-21

### Added

- Task queue: append-only `events.jsonl`, a derived `task.yaml`/`task.json` projection, replay,
  idempotent `submit` keyed by `(source.kind, source.ref)`, one-owner claims, and a derived SQLite
  index for `status`.
- Typed state machine with every legal edge and a terminal blocked state.
- Path policy: deny wins, test paths denied by default, `..`, absolute paths, drive letters and
  control characters refused, case-insensitive matching on every platform.
- Flow schema with node kinds, acyclic edges, repair and gates; the shipped `fix-issue` flow.
- `works` CLI: `submit`, `status`, `task`, `trace`, `approve`, `run` (with `--dry-run`),
  `policy check`, `ledger`, `schema`, `doctor`, `version`; `--json` and stable exit codes.
- Supervisor: reproduce → plan gate → build → test → scenarios → verdict → evidence, with a
  bounded harness port and an append-only ledger.
- Evidence: computed page bound to the diff by SHA-256, with per-scenario results, commands,
  policy, cost and the diff.
- Fake harness that replays a recorded trace; a fixture repository with a planted bug, two P0 and
  one P1 scenario, and traces for a good fix, a sneaky fix, a test edit and an abstention.
- Doctor checks for Python, git, workspace, flow, harness, container, credentials, scenarios and
  quarantine.
- Quarantine lists and scenario sets must live outside the repository; reading one inside is
  refused.
- CI: ruff, mypy strict, pytest with an 80% floor, benchmark job, bandit, gitleaks; weekly
  mutation gate (71.8% on state, policy and queue) and supply-chain audit.
- Live builder: `works run --live` drives `openjiuwen`'s Claude Code harness on the native
  `claude.exe` and the DeepSeek Anthropic-compatible endpoint; the worktree is edited in place,
  policy checks touched paths, and model/tokens/USD are recorded.
- Memory: finished runs are posted to PPMA as `works.run_finished` events with deterministic ULIDs,
  a registered manifest and an app token.
- Factory parity: versioned prompt registry with a recorded hash; structured findings with
  confidence/uncertainty; `works metrics` for attention, waiting and cost; proof sections for
  findings and residual risk; Mira, the magpie courier, as the product mascot.
- ADRs 008–010, the runbook entries for live harness and PPMA failures, and
  `docs/review-4-factories.md`.
