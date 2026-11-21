# Architecture decisions

Short records of choices that are expensive to reverse. One file per decision, numbered, never
deleted — a superseded decision is marked as such and points to its replacement.

| ADR | Decision | Status |
|---|---|---|
| [001](001-engine-in-python.md) | The engine is Python | accepted |
| [002](002-files-and-jsonl.md) | Files and JSONL before a database | accepted |
| [003](003-cli-first-gui-later.md) | CLI is the first window | accepted |
| [004](004-isolation-boundaries.md) | Worktree is not a security boundary | accepted |
| [005](005-verifier-independence.md) | The verifier is independent in runtime and provider | accepted |
| [006](006-sqlite-derived-index.md) | SQLite is a derived index, not the source of truth | accepted |
| [007](007-cli-startup-budget.md) | The CLI starts without a framework | accepted |

Format: context, decision, consequences, alternatives rejected.
