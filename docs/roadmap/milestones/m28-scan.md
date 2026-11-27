# M28 — proactive scan (design)

Status: complete (28.1–28.5).

## Why

Every intake so far waits for a report. A regression that nobody has noticed yet is the cheapest kind
of fix, and the product already has a check harness and a queue to act on it. M28 adds one explicit
command that runs a repository's own check, remembers what was failing, and files a task only for a
**new** failure.

## Decision

**The scan is explicit and local.** `works scan --repo PATH --command "…"` runs once. There is no
daemon poller yet: a scheduled scan would multiply cost and noise before anyone has watched the
baseline behave.

**The baseline is the noise guard.** The last failure ids for `(repo, command)` live in
`~/.works/state/scan/<digest>.json`. A failure that was already known is not filed again; a failure
that disappears is removed; a first scan on a red repository files the failures it finds, because
there is nothing to compare with.

**One task per failure id.** Ids come from pytest-style `FAILED tests/x.py::test` and `ERROR …`
lines. A non-zero exit with no parseable ids becomes one stable `command-<hash>` id derived from the
exit code and the last lines of output — the same broken build does not create a task every day.

**A scan never starts a run and never opens a gate.** It submits a normal `fix-issue` task with the
command and the failing id as the reproduction hint. The scheduler, budget and both human gates are
unchanged.

**Dry run is free.** `--dry-run` prints the diff against the baseline and writes neither a task nor a
baseline, which is the safe way to adopt a noisy check.

## What a task carries

- `source.kind: detector`, `channel: scan`, `ref: scan:<failure>`;
- `severity: S3` — a scan finding is not a customer incident;
- labels `scan`;
- a reproduction hint naming the command and the failure;
- a dedupe key `scan:<repo+command digest>:<failure>`.

## Limits

- Only pytest-style failure lines are parsed; other runners fall back to one stable command failure.
- No scheduling, no parallel shards, no flaky-test suppression beyond the baseline.
- No automatic repair: the task goes through the normal pipeline and the two gates.
- The scan runs the command with the user's OS permissions; use a repository and a command you trust.

## Acceptance

| case | test |
|---|---|
| failure ids parse and deduplicate | `test_scan.py` |
| a new failure creates one task | `test_scan.py` |
| the same failure is not filed twice | `test_scan.py` |
| a fixed failure leaves the baseline | `test_scan.py` |
| a green run clears the baseline | `test_scan.py` |
| an unparseable failure is one stable task | `test_scan.py` |
| a dry run writes nothing | `test_scan.py` |
| the baseline is keyed by repo and command | `test_scan.py` |
| the CLI reports JSON and dedupes | `test_scan.py` |

## Work breakdown

| item | days |
|---|---|
| 28.1 baseline, parsing and scan | 1.0 |
| 28.2 task creation and dedupe | 0.5 |
| 28.3 CLI and dry run | 0.5 |
| 28.4 docs and tests | 0.5 |
| **total** | **2.5 (~3 with contingency)** |
