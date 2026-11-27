# Pipeline benchmark

```bash
works bench --dataset cases.jsonl
works bench --dataset cases.jsonl --json
```

Runs the real pipeline over a small local dataset and reports how often it reaches the expected state
with a bound proof.

## Dataset

One JSON object per line:

```json
{"id":"add-negative","repo":"../fixtures/fixture-repo",
 "scenario_set":"scenario.yaml","trace":"fix-add.json",
 "expect_state":"proved","expect_verdict":true}
```

| field | meaning |
|---|---|
| `id` | case name, unique in the dataset |
| `repo` | path to a git repository, absolute or relative to the dataset |
| `scenario_set` | path to the scenario YAML |
| `trace` | recorded harness trace (deterministic, no model) |
| `ref`, `title`, `product`, `flow` | optional task fields |
| `expect_state` | expected terminal state, default `proved` |
| `expect_verdict` | `true`, `false` or `null` to ignore the verdict |

## What runs

Each case gets its own home, queue and supervisor. The harness is the fake trace, so a case costs
nothing and the result is reproducible. The pipeline still runs reproduction, planning, build, checks,
the independent challenge, the verdict and the proof.

A case is **resolved** only when the state matches, the verdict matches when expected, and the proof is
bound. A green run without a proof is not resolved.

## Output

```text
ok   add-negative · proved · verdict True · proof bound · $0.00
FAIL hostile      · blocked · verdict False · proof unbound · $0.00
bench: 1/2 resolved (50%) · 1 proof(s) bound · $0.00
```

`--json` returns the same numbers plus one object per case. `--keep` leaves the isolated homes under
the working directory for inspection.

## Not claimed

- This is not a SWE-bench score. The dataset is yours; a SWE-bench converter is not built.
- The fake harness means the benchmark measures the pipeline, not a model.
- A failing case does not fail the command; wiring it into CI is a separate decision.
