# M30 — pipeline benchmark (design)

Status: complete (30.1–30.4).

## Why

The remaining recommendation was "a number buyers can compare". A real SWE-bench run needs the
dataset, the repositories, a live model and hours of compute; none of that belongs in a local CI gate.
What the product can do honestly is run **its own pipeline** over a set of local cases and report how
often it reaches the expected state with a bound proof. That is a regression instrument first and a
credibility instrument second.

## Decision

**A case is a line of JSON.** It names a repository, a scenario set, a recorded harness trace and the
expected outcome:

```json
{"id":"add-negative","repo":"../fixtures/fixture-repo","scenario_set":"scenario.yaml",
 "trace":"fix-add.json","expect_state":"proved","expect_verdict":true}
```

**Each case runs in its own isolated home** through the real supervisor, the real queue and the real
proof code. The harness is the fake trace, so the benchmark is deterministic and costs nothing; it is a
pipeline test, not a model benchmark.

**A case is resolved only when all three hold:** the terminal state matches, the verdict matches when
expected, and the proof is bound. A green test with no proof is not resolved.

**The report is small and honest:** resolved / cases, rate, bound proofs, total USD, and one line per
case with state, verdict, proof and error. `--keep` leaves the isolated homes for inspection.

## What it is not

- Not a SWE-bench score and not a leaderboard entry. The dataset is yours; a SWE-bench adapter is not
  built.
- Not a model comparison: the fake harness is deterministic and free.
- Not a gate: a failing case prints a failure and exits 0; CI integration is a later decision.

## Acceptance

| case | test |
|---|---|
| a good and a hostile case are both scored | `test_bench.py` |
| an unexpected state is not resolved | `test_bench.py` |
| a missing repository is a case failure, not a crash | `test_bench.py` |
| relative paths resolve against the dataset | `test_bench.py` |
| a malformed dataset names the line | `test_bench.py` |
| the CLI accepts an empty dataset and reports zero | `test_bench.py` |

## Work breakdown

| item | days |
|---|---|
| 30.1 case format, loader and isolated homes | 0.7 |
| 30.2 supervisor run and scoring | 0.8 |
| 30.3 CLI and report | 0.5 |
| 30.4 docs and tests | 0.5 |
| **total** | **2.5 (~3 with contingency)** |
