# ADR-001 — The engine is Python

**Status:** accepted · 2026-11-21

## Context

The engine must drive an agent harness. The harness we are required to use, `openjiuwen`, is a
Python library exposing `HarnessProtocol` in-process: `start`, `send`, `events`, `turn_events`,
`export_checkpoint`. Target repositories for v0 are also Python.

## Decision

The engine is Python 3.12, packaged with `uv`, typed with mypy strict.

## Consequences

- Direct access to harness events, checkpoints and cost, without parsing CLI output.
- The same language as the repositories it tests, so running their suites needs no bridge.
- A future web UI is a separate app; the engine exposes JSON and HTTP when needed.
- Slower cold start than a compiled binary; mitigated by a 300 ms budget.

## Alternatives rejected

- **Go/Rust**: fast binaries, but the harness would be reachable only through a subprocess, losing
  events and checkpoints.
- **TypeScript**: same problem, plus two runtimes to maintain.
