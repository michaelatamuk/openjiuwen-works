# ADR-013 — Readiness before autonomy; the codebase is the agent's largest input

**Status:** accepted · 2026-11-21

## Context

Lauren Tan's SpaceX SI talk (`docs/archive/reviews/review-5-slop.md`) describes a trust pyramid: deterministic code
— APIs, architecture, lint rules, types, compilers, tests — is the strongest control; verification
(runtime, property, formal) is the next layer; prose (rules, skills, `AGENTS.md`, comments) is the
weakest. The team ships thousands of pull requests with a low revert rate because the repository
makes good changes the default. Their warning is direct: if the inner coding loop produces slop,
automating that loop produces more slop and consumes more tokens.

Works already has trusted-base checks, exact-commit binding, a verifier, a challenger and a proof.
It does not yet ask whether the target repository is ready for autonomy, and it does not show
feature-level runtime evidence.

## Decision

- **Readiness is a gate.** `works readiness` checks lint, format, types, the fast test path,
  architecture boundaries, known suppressions, a `verify` command and a feature map. A red gate
  refuses automation; the next task is the missing check, not another prompt.
- **The codebase is the input.** Every repeated finding, escape or revert becomes a deterministic
  check — lint rule, structural test, API change or scenario — reviewed like code. Old occurrences
  are cleaned up in the same change or a linked task. A suppression needs an owner, a reason and an
  expiry.
- **Feature map and runtime artifacts.** A versioned `features/<product>.yaml` describes features
  from the user's point of view. A `preview` node drives the feature and attaches a screenshot,
  video, log and trace. The proof shows covered and uncovered features.
- **Architecture guardrails** — import boundaries, dependency rules, module fan-in and structural
  tests — run deterministically in the repository and in the verifier.
- **Verification cost is split** into builder, challenger and verifier tokens/USD. Verification
  often dominates; that is a measurement, not a target.
- **Formal methods are optional layers** for high-risk flows. They never replace the verifier, the
  feature map or the two human gates.
- **Auto-merge stays out of scope** until readiness, evals and a green escape window hold.

## Consequences

- A repository can be refused before a run starts, which is cheaper than a bad run.
- Readiness and architecture checks become code shared by the factory and the product; they are
  versioned, tested and reviewed.
- The proof becomes a set of verification artifacts, not only a diff and a verdict. The read-only
  GUI preview can show readiness, feature coverage, risk and decisions.
- More work lands before the first automated change; the payoff is fewer review comments and a
  lower revert rate.
- A feature map is another artifact to keep current; stale ids fail the scenario instead of silently
  drifting.

## Alternatives rejected

- **Prompt-first reliability**: rules and comments are unenforceable and agents use them as escape
  hatches.
- **Automate first, clean later**: produces more slop at higher cost and hides the weak inner loop.
- **Readiness as a warning**: a warning is ignored under delivery pressure; the gate must refuse.
- **Formal verification everywhere**: expensive, narrow and not a substitute for evidence.
- **Auto-merge now**: the public numbers are self-reported and our own evals are not there yet.
