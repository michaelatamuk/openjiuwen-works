# Sources

Every claim in the deck should point here or to a demo step.

## Product and story

| Source | Use |
|---|---|
| `README.md` | one-line promise, problem, flow, demo commands |
| `docs/start/concepts.md` | ten stages, two gates, plain language |
| `docs/start/status.md` | what is built and the one open item |
| `docs/design/architecture.md` | processes, layers, one run, data, invariants |
| `docs/reference/lifecycle/proof.md` | what the proof binds and verifies |
| `docs/reference/lifecycle/gates.md` | plan/release decisions, identity, TTL, quorum |
| `docs/reference/lifecycle/check.md` | verifier, trusted base, P0/P1 |
| `docs/reference/platform/reliability.md` | crash, retry, idempotency, backpressure |

## Comparisons

| Source | Use |
|---|---|
| `docs/design/strategy/positioning.md` | Works vs Orbit, harness, three contracts, what is built/proposed |
| `docs/guides/integrations/live-harness.md` | Works vs openJiuwen; providers; challenger |
| `docs/guides/integrations/swarm.md` | Works vs JiuwenSwarm; external builder boundary |
| `docs/design/strategy/competitor-analysis.md` | Devin, Claude Code/Codex, Copilot Workspace, OpenHands, OpenAI factory |
| `docs/archive/reviews/review-4-factories.md` | two agent factories, attention and review bottleneck |
| `presentation/03-works-vs.md` | the direct three-way comparison |
| `presentation/03-comparisons.md` | category matrix and "why not add modules" |

## Decisions

| ADR | Use |
|---|---|
| `docs/design/adrs/004-isolation-boundaries.md` | worktree is not a security boundary |
| `docs/design/adrs/005-verifier-independence.md` | independent verifier |
| `docs/design/adrs/008-live-harness.md` | openJiuwen harness, not a patch generator |
| `docs/design/adrs/010-factory-and-attention.md` | task graph, waits, no org chart |
| `docs/design/adrs/012-trusted-base-and-risk.md` | checks outlive changes; risk decides who approves |
| `docs/design/adrs/016-local-daemon.md` | one daemon owns one home |
| `docs/design/adrs/019-job-executor.md` | one bounded thread pool |
| `docs/design/adrs/024-scheduler-actor.md` | scheduler runs, never decides |

## Assets

Copied into `presentation/assets/` for the deck; the originals stay in `docs/assets/`.

| Asset | Use |
|---|---|
| `assets/why-works/00`–`07` | three products, three kinds of done, separation, two signatures, why pay |
| `assets/diagrams/the-point.png` | the bottleneck |
| `assets/diagrams/software-factory-flow.png` | the ten stages |
| `assets/diagrams/software-factory-queue.png` | the queue |
| `assets/diagrams/built-on-openjiuwen.png` | layers: models, harness, Works |
| `assets/diagrams/positioning-*.png` | Works vs Orbit, contracts, build stage |
| `assets/screens/story.png` | the product screen |
| `assets/brand/banner.svg`, `banner-dark.svg` | title and closing |

## Assets still to draw

- **Proof binding**: diff + checks + verdict + event root + page fingerprint → one commit.
- **Not a plugin**: a product X with the lifecycle modules pulling it into a different product.
- **Comparison matrix**: Works vs harness, horizontal app, agent factory, tracker + CI.
- **Built vs proposed**: a clean two-column slide, no hand-waving.

## Claims to verify before the final deck

- The current test, coverage and route numbers.
- The exact live-harness cost/time numbers if quoted.
- Whether the audience may see real task names and real screenshots.
- Whether Orbit is in the room; if yes, use the collaborative framing from `positioning.md`.
