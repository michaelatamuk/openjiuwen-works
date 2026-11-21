# Demo — M0 and the walking skeleton

What it proves, in one run:

1. A signal becomes a task; the same signal twice returns the same task.
2. `--dry-run` shows the nodes and the scenarios without changing state.
3. A change to `tests/` is refused by policy before any command runs.
4. The loop reproduces the bug, applies a recorded proposal, passes the visible tests, passes two
   P0 and one P1 holdout scenario, and produces a proof page.
5. The append-only ledger gets one row: `proved / allow / 1200 tokens / $0.0120`.

## Run it

```powershell
uv sync --extra dev
powershell -ExecutionPolicy Bypass -File scripts/demo-m0.ps1
```

The script creates a temporary workspace and a committed copy of `fixtures/fixture-repo`, runs the
commands above, prints the proof, and exits non-zero if any check is wrong.

## Transcript (abridged)

```text
== 1. submit ==
task: t-658256456364 (created: True)

== 2. dry run ==
nodes and scenarios printed above; the task is still queued

== 3. a test edit is refused before any command runs ==
violation: tests/test_core.py / denied by policy
policy exit code: 3 (expected 3)

== 4. the whole loop with a recorded harness trace ==
run r-20261121T024507-ab8397: proved (completed) - 3975 ms - 1200 tokens - $0.0120
proof: ...\runs\r-20261121T024507-ab8397\evidence.md
run exit code: 0 (expected 0)

== 5. status and ledger ==
id              state   flow       source         attempts  owner
t-658256456364  proved  fix-issue  manual:DEMO-1  1         -

ts                         task            run                       state   verdict  tokens  usd
2026-11-21T02:45:11+00:00  t-658256456364  r-20261121T024507-ab8397  proved  allow    1200    0.0120
```

## Measured on the development host

| Budget | Measured | Target |
|---|---|---|
| CLI start (`works --help`) | 206 ms | < 300 ms |
| `status` logic, 10 000 tasks | 59 ms | < 100 ms |
| Evidence render | 0.02 ms | < 1 s |

Run `python scripts/bench.py` to reproduce. Process startup on Windows is noisy; the benchmark
reports the best of several runs and the in-process logic separately.

## What is deliberately fake

- The harness replays `fixtures/traces/*.json`; no model is called.
- The verifier is the local scenario runner; the container and the independent provider land in M2.
- The release step stops at `proved`; publishing a branch and a PR lands in M3.
