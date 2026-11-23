# Review 5 — All Code Is Slop (Except Mine)

**Source:** Lauren Tan (poteto), SpaceX SI / Grok Bot, AI Engineer, 14 November 2026.
<https://www.youtube.com/watch?v=O_zcc6Xl12g> · transcript reviewed 21 November 2026.

This is a practitioner talk, not a controlled study. The numbers are self-reported: 3,000 personal
pull requests in a month, 11,000 for the team, about 227 contributors, a stable release roughly once
a day and a revert rate around 0.5%. The useful part is the mechanism, not the multiples.

## Thesis

Trust in agents is built by the environment, not by prompts. The trust pyramid, strongest first:

1. **Deterministic code** — API design, architecture, refactoring, lint rules, type systems,
   compilers, tests.
2. **Verification** — runtime checks, property-based tests, formal methods where they fit.
3. **Prose** — rules, skills, `AGENTS.md`, comments.

The codebase is the agent's largest input. Agents copy existing patterns, including workarounds,
deprecated code and comments that justify a shortcut. Every correction should become a deterministic
check or a better API; otherwise the same mistake returns. If the inner loop produces slop,
automating it produces more slop at higher token cost.

## What the talk demonstrates

- Nuance-heavy APIs (for example `useEffect`) are banned in product code and replaced by lint rules.
- Directory structure carries context; a dependency-graph check forbids imports between Electron main
  and renderer.
- Most comments are banned because they are unenforceable escape hatches; lint errors tell the agent
  to fix the root cause.
- Review moves to verification artifacts: videos, screenshots, diagrams, formal proofs.
- Runtime verification uses the running app and the Chrome DevTools protocol; a **feature map** gives
  agents and reviewers shared names for user-facing features; custom CLIs are reusable and testable.
- Formal methods are a layer, not a silver bullet: TLA+ for cross-device notification flows, Lean for
  a virtualization library, property-based UI testing for extra coverage.
- About 70% of daily tokens go to verification (Cindy's report, echoed by the speaker).
- High volume does not have to raise the revert rate when the codebase makes good changes the default.

## What Works takes

| Idea | Where it lands |
|---|---|
| Readiness before autonomy | `works readiness`; T2.18; D17 |
| Codebase is the input; corrections become checks | T4.6; D18 |
| Feature map + runtime artifacts | T2.19; T1.24 preview |
| Architecture guardrails | T2.18 |
| Suppression-aware suspicious list | T1.11 |
| Verification cost split | T1.25 |
| Performance budgets | T3.17 |
| Formal/property as optional high-risk layers | T2.16; §6.9 |

## What Works does not take literally

- **Ban 99% of comments.** We flag comments that justify a workaround or a suppression, not all
  comments. Documentation and decisions still belong in the repository.
- **Auto-merge.** The public numbers are self-reported; our own evals and a green escape window are
  not there. The two human gates remain.
- **Formal verification as mandatory.** High-risk flows only; it is expensive and narrow.
- **The multiples as targets.** 11,000 PRs or 0.5% revert are hypotheses to test in our environment,
  not benchmarks to copy.

## Why it matters for the roadmap

The talk validates the gate-hardening batch: trusted-base checks, exact-commit binding, risk rating
and verification artifacts all move in the same direction. The two gaps it exposes are **repository
readiness** and **feature-level runtime evidence**. Closing them makes the read-only GUI preview
meaningful: readiness, feature coverage, risk and proof in one window.
