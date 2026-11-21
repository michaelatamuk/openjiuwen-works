# ADR-004 — Worktree is not a security boundary

**Status:** accepted · 2026-11-21

## Context

v0 isolates tasks with `git worktree` on the developer's machine. That separates files, not
privileges: the agent runs as the same OS user and can read anything that user can read, including
the holdout scenarios if they sit on the same disk.

## Decision

- The builder runs on the host with a pinned working directory, path-escape refusal and a network
  allowlist; it has no production credentials.
- The verifier runs in a container with only the worktree mounted read-only and the scenarios
  mounted inside that container alone.
- Known limitation, written down: a determined builder can still read the host filesystem.
- v1 moves the builder into its own container or VM; the interface does not change.

## Consequences

- Real isolation arrives with containers; until then, policy and detection carry the weight.
- Leak tests grep every builder-readable artifact for scenario strings.
- The scenario directory lives outside the repository and is never committed.

## Alternatives rejected

- **Second OS user on Windows**: fiddly, and it still shares the disk.
- **Prompt-level rules**: a request, not a boundary.
