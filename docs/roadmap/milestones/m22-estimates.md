# M22 — estimating the work (design)

Status: planned. M21 ships with coarse grouped medians; M22 makes the estimate good enough to order
and fit work.

## Why

M21 needs two numbers per task: **how long** and **how much**. They answer three questions:

- does the run fit the remaining daily budget (`p90_usd ≤ remaining`);
- does it fit before a maintenance window (`p90_min ≤ minutes_until_blackout`);
- who goes first when risk is equal (short first, without starving the long one).

The same numbers are the most useful thing the UI can show: "~40 min, $1.20, from 12 similar runs"
removes most of the "why is it stuck" questions. A wrong estimate is worse than no estimate, so the
output is a **distribution with a confidence**, never a single promised minute.

## What we already store

No new data collection is needed to start:

| source | fields |
|---|---|
| `evidence.json` | `duration_ms`, `tokens`, `usd`, attempt count, verdict, `not_tested` |
| `run.json` | flow, base commit, risk, plan id |
| plan | steps, files, risk, diff estimate |
| reproduce | time to reproduce, runner, failures |
| release packet | plan estimate **and** the actual, already compared |

## The estimate

```python
@dataclass(frozen=True)
class Estimate:
    p50_min: float
    p90_min: float
    p50_usd: float
    p90_usd: float
    confidence: float     # 0..1, from sample count and dispersion
    samples: int
    source: str           # "history" | "knn" | "model" | "plan" | "static"
```

Recorded on the claim and in the ledger, so a later review can compare estimate with fact.

## Features

**Before the run (intake)** — cheap and available for every task:

- text: length, stack traces, code blocks, mentioned files, links to CI;
- product, repository, labels, source, flow;
- area from paths in the ticket (overlap with the path policy);
- similarity to past tickets: BM25 over title and body, path Jaccard.

**After reproduce** — the strongest cheap signal:

- did it reproduce, how long it took, how many tests failed;
- language, runner, repository size, whether setup was needed.

**After the plan** — the second update, just before build:

- number of steps and files, risk, new tests, migrations, config;
- optional `estimate: {minutes, usd, rationale}` from the planner, used as a **feature**, not as the
  answer.

## Method ladder

Chosen by data volume, not by ambition:

1. **Cold start** — median by `repo × flow × risk`, else a static per-flow default. Wide interval,
   `confidence ≤ 0.3`.
2. **Grouped history** (M21) — quantiles per group with `min_samples`; the source is `history`.
3. **Similar tasks** (M22) — k-NN over ticket similarity + path overlap + risk + plan size; quantiles
   of the neighbours, interval widened when `k` is small. Explainable: "12 similar tasks".
4. **Model** (only past a few hundred runs) — gradient boosting with quantile loss (p50/p90) on tabular
   features. No deep learning: the gain does not justify the opacity.

The estimate is recomputed after the plan, and the claim records which version it used.

## Calibration and backtest

Offline, over stored runs, before any ordering trusts the numbers:

- **pinball loss** for p50 and p90;
- **coverage of p90** — should be 85–95%; 60% means the tail is a lie;
- **tail misses** — the share of runs above p90 (this is the expensive error);
- **per-group** results (`repo`, `flow`, `risk`), because a good global score can hide a bad group;
- **no leakage** — only features known before the run starts.

A backtest command (`works estimate backtest`) prints the table and fails a threshold in CI, so the
estimator cannot silently rot.

## How the scheduler uses it

Once the estimates exist, "smart" is a deterministic cost model, not a learned ranker:

| decision | rule |
|---|---|
| budget | `p90_usd ≤ remaining` |
| window | `p90_min ≤ minutes_until_blackout` |
| ordering | `value_density = (w_risk·risk + w_urgency·urgency) / p50_usd` |
| filling a window | greedy/knapsack over `p50_min`: two short tasks beat one that does not finish |
| anti-starvation | age boost is a hard floor, never a model input |

Every component is written to the ledger, so "why this task" stays answerable.

## Shadow first, then trust

Same pattern as the LAIX decision layer:

```yaml
order:
  mode: rule        # rule | shadow | learned
```

- `rule` — the deterministic chain from M21;
- `shadow` — the model computes its order in parallel, starts nothing, and logs "would pick X, rule
  picked Y";
- `learned` — enabled only after the shadow beats the rule on our own metrics.

Promotion needs **all** of:

- ≥ 4 weeks or ≥ 50 claims of shadow data;
- p95 wait not worse, and p50 wait better by a meaningful margin;
- no new starvation incidents;
- `$` per `proved` change not worse;
- calibration inside the coverage band.

If any fails, the answer stays `rule` and the page says why.

## Guardrails

- **Goodhart:** the estimate is computed from evidence, not from the agent's self-report; a planner
  estimate is one feature among many.
- **Drift:** history is windowed (last 20 runs per repo, at most 90 days); a big refactor resets the
  window and lowers confidence.
- **Heavy tail:** ordering uses p50, fit and budget use p90; neither uses the mean.
- **Small n:** confidence is shown, and a low-confidence estimate is not allowed to reorder a
  high-risk task — it only feeds the display.
- **No preemption:** estimates decide what not to start; they never stop a running job.

## Non-goals

- story points, velocity, or per-person productivity metrics;
- price or schedule forecasting beyond the next run;
- a cloud model, an embedding service, or an external dataset;
- deep learning;
- estimating delivery/deploy/confirm time (they are seconds, not minutes).

## Acceptance

| proof | expected |
|---|---|
| cold start | every task gets an estimate; low confidence is shown, not hidden |
| similar tasks | a ticket with 12 neighbours reports the neighbour count as the sample size |
| plan update | the post-plan estimate replaces the pre-run one and both stay in the ledger |
| backtest | pinball loss and p90 coverage computed per group; a bad estimator fails the command |
| fit decisions | a task whose p90 does not fit the window or budget is refused with the reason |
| ordering | equal risk, two sizes: the short bucket first; the long one still runs within the boost |
| shadow | the model's order is logged, nothing is claimed differently |
| promotion | `learned` cannot be enabled without the shadow evidence |
| monotonicity | more risk or more age never worsens a task's position |

## Work breakdown

| # | Work | Days |
|---|---|---|
| M22.1 | `Estimate` type, storage, ledger recording | 1 |
| M22.2 | pre-run features from intake, repo and path overlap | 2 |
| M22.3 | post-plan estimate update and planner feature | 1 |
| M22.4 | backtest harness: pinball, coverage, per-group, CI threshold | 2 |
| M22.5 | k-NN over similar tasks; grouped medians as the control | 2 |
| M22.6 | `order.mode: shadow` and the promotion report | 2 |
| M22.7 | docs and acceptance | 1 |

**~11 engineer-days**, or **~13 with contingency**.
