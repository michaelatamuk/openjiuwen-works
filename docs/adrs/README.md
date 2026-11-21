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
| [008](008-live-harness.md) | The builder is a real openjiuwen harness, not a patch generator | accepted |
| [009](009-ppma-memory.md) | PPMA owns memory; Works reports finished runs | accepted |
| [010](010-factory-and-attention.md) | A factory is a task graph with waits, not an org chart | accepted |
| [011](011-laix-decision-layer.md) | LAIX is the optional decision layer, not the factory | accepted |
| [012](012-trusted-base-and-risk.md) | Checks outlive changes; risk decides who approves | accepted |
| [013](013-readiness-before-autonomy.md) | Readiness before autonomy; the codebase is the agent's largest input | accepted |
| [014](014-one-proof-two-readings.md) | One proof, two readings: Story for people, Evidence for engineers | superseded in part by 015 |
| [015](015-story-line.md) | The task is a line; Mira is the courier | accepted |

Format: context, decision, consequences, alternatives rejected.
