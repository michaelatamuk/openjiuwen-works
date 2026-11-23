# Review 2 — what similar teams do that the plan does not

Sources: Stripe Minions (part 2, 2026), Ramp Inspect (engineering post, 2026), Warp Factories
(docs and engineering blog, 2026), StrongDM (2026), OpenAI Performance Factory (2026).

Each row is a practice, why it exists, and what changes in our plan.

## 1. Reproduce before fixing — Ramp Inspect

Ramp's agent reproduces the failure in a sandbox and only ships a fix once the reproduction test
passes. In their security work, a finding that already passed was discarded as a false positive.

**Why it matters:** without a failing reproduction we cannot tell a real fix from a plausible edit,
and the proof page becomes an opinion.

**Plan change:** new step between "find the code" and "plan": **reproduce** — write a failing test or
scenario, prove it fails on the base commit, and store it. The verifier reuses it.

## 2. Blueprints — Stripe

Stripe's workflows are state machines with two node types: deterministic nodes (lint, push, run CI)
that never call a model, and agentic nodes (implement, fix CI) that do. Deterministic nodes are
unconditional; the agent cannot skip them.

**Why it matters:** it guarantees the boring, critical steps happen every run and saves tokens.

**Plan change:** define `flows/*.yaml` as a node graph with `kind: deterministic|agentic`, and state
that deterministic nodes are enforced by the runner.

## 3. Bounded repair — Stripe

One repair attempt, one CI rerun, then the branch returns to a human. Open-ended retries make the
code worse while fixing symptoms.

**Plan change:** replace "retry budget" with an explicit limit (1 repair + 1 CI), and treat "needs a
person" as a normal outcome.

## 4. Prepared environment — Ramp

Prebuilt images with dependencies installed, refreshed every 30 minutes; the agent starts reading
immediately and edits are blocked until sync completes.

**Why it matters:** time-to-first-token and missing dependencies are the most common silent killers.

**Plan change:** add a task to build a prepared environment for the target repo and measure cold
start; block edits until the worktree is synced.

## 5. Access by infrastructure, not prompts — Stripe

Agents run in QA-only environments without production credentials. The boundary is the environment,
not a rule in the prompt.

**Plan change:** state explicitly that v0's worktree is **not** a security boundary; add a restricted
user/env task and forbid production credentials in the builder.

## 6. Scorers on a sample — Warp

Scorers grade a sample of runs (default 25%) against written criteria; failures feed self-improvement
and benchmarks.

**Plan change:** add a scorer with sampling and a rubric, separate from the scenario verdict.

## 7. Benchmarks on your own tasks — Warp

Replay past runs at their exact initial state to compare prompt or model changes; they cut cost 63%
on some task types this way.

**Plan change:** add a five-task benchmark suite built from our own runs, used before changing a
prompt or model.

## 8. Self-improvement as a PR — Warp

Observer agents batch failures and propose changes to the factory definition; every proposal arrives
as a pull request for review.

**Plan change:** our learning loop must produce a diff (rule, test or scenario), reviewed like code.

## 9. Curated tool subset — Stripe

Hundreds of tools exist; each run gets a small default subset, extended per task.

**Plan change:** add a task to define the default toolset and the per-flow extension.

## 10. Directory-scoped rules — Stripe

Rules are attached to subdirectories and file patterns, not loaded globally.

**Plan change:** prompt assembly must include path-scoped rules only.

## 11. Abstain on non-bugs — Ramp

Seed a known regression and a similar-looking non-bug; the system must fix one and abstain on the
other.

**Plan change:** add this as a verifier acceptance test.

## 12. CI cost is a real budget — Stripe

CI is the expensive part; runs are capped.

**Plan change:** add CI minutes to the budget model, not just tokens and USD.

---

## What we deliberately do not copy

- **Full production context** (Ramp): they are an established org with sanitized replicas. We start
  with a public OSS fork and no production data.
- **Multiplayer sessions** and a control-room UI: out of scope for v0.
- **500 internal tools**: we have four products and a shell.
