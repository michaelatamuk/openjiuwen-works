# ADR-007 — The CLI starts without a framework

**Status:** accepted · 2026-11-21

## Context

The standard budgets CLI cold start under 300 ms. A first implementation used Typer and Rich. With
eager imports of the domain modules, `works --help` took 775 ms on the development host, and
`status` took 570 ms. The interpreter baseline alone is about 80–130 ms on Windows.

## Decision

- `argparse` from the standard library; no CLI framework and no terminal-styling dependency.
- Domain modules are imported inside the command that needs them.
- `works status` reads the derived SQLite index through `works/fast.py`, which imports only the
  standard library.
- Hot paths are measured by `scripts/bench.py` and guarded by `tests/test_performance.py`.

## Consequences

- Measured on the development host: `works --help` 206 ms, empty `status` 244 ms including the
  process, `status` logic at 10 000 tasks 59 ms, evidence rendering 0.02 ms.
- Help output is plain text, not Rich panels. Machine output is unchanged JSON.
- A framework can return later for a real GUI; the CLI contract (`--json`, exit codes) is stable.

## Alternatives rejected

- **Typer + lazy imports only**: typer pulls Rich for help, and the budget is tight on Windows.
- **Click**: lighter than Typer but still a dependency for no capability argparse lacks here.
- **`--json` only**: humans need a readable table; plain text costs nothing.
