# Objections

Short answers for the questions that decide the meeting. Each answer has a source or a demo step.

## "Why not just use Orbit?"

Orbit is horizontal: rooms, people, coordination, shared memory, routing. Works is vertical: one
change, per-language checks, a proof bound to the commit, two human gates. They compose through three
narrow contracts; they do not replace each other. If you merge them, Orbit stops being generic and
Works stops being strict.

Source: `03-works-vs.md`, `docs/design/strategy/positioning.md`.

## "Why not add a queue and a proof page to openJiuwen?"

A queue is the small part. You also need a durable state machine, worktrees, policy, an independent
verifier, an evidence schema with hashes, gate identity and expiry, delivery markers and a
confirmation loop. That changes the harness contract, its latency and its failure model. The harness
stops being a harness.

Source: `03-works-vs.md`, `docs/guides/integrations/live-harness.md`.

## "Why not use JiuwenSwarm as the factory?"

Swarm is capacity: a leader splits work and subagents build. A leader cannot sign off its own work.
Works owns the plan gate, policy, verification, proof, release gate, delivery and confirmation.
Swarm is an external builder behind `works.swarm.v1`; the worktree is the only shared path.

Source: `03-works-vs.md`, `docs/guides/integrations/swarm.md`.

## "Why not Devin or Factory.ai?"

They are agent factories, usually cloud or self-hosted. They can plan, execute and review. Works
differs on the product boundary: local-first, one home, open harness choice, a proof bound to the
commit and two human gates that are the product, not a settings page. If a vendor adds all of that,
it becomes a different product for a different buyer.

Source: `03-comparisons.md`, `docs/design/strategy/competitor-analysis.md`,
`docs/archive/reviews/review-4-factories.md`.

## "Why not Jira + GitHub Actions + an agent?"

The tracker holds state, CI runs checks, the agent writes code. None of them owns the plan decision,
the independent verification, the proof binding or the release decision. You would have to add all
four, and then you have built an agent factory.

Source: `03-comparisons.md`.

## "Isn't this just an agent wrapper?"

No. Remove the harness and Works still has a queue, policy, gates, proof, delivery and confirmation.
Remove the lifecycle and nothing is left. Works has no model, no agent loop and no tool runtime.

Source: `03-works-vs.md`.

## "Why two human gates? Isn't that slow?"

The evidence from agent factories is that review and merge are the scarce steps, not diagnosis.
Autonomy increases the number of changes that reach review; it does not increase the number of people
who can approve them. The two gates are where judgement changes the outcome. Everything else is
automatic.

Source: `docs/archive/reviews/review-4-factories.md`, `docs/reference/lifecycle/gates.md`.

## "Why local-first? Cloud is easier."

The source, the diffs and the proofs stay on the machine. One daemon owns one home; the model
provider receives only the context the builder sends. Local-first is also a product boundary: the
buyer keeps the repository, the credentials and the evidence.

Source: `README.md`, `docs/reference/platform/reliability.md`.

## "Why won't the big vendors just add this?"

They can. The argument is that doing so changes their product: their unit is the turn or the ticket,
their distribution is the model or the cloud, and their buyer is asking "can it write the change?",
not "can I stand behind the change?". A proof-bound lifecycle adds states, waits and human decisions
that are not a natural upsell for a tool measured by turns.

Source: `03-comparisons.md`.

## "What is the moat?"

The binding, not the UI: checks read from the base commit, an independent verifier, a proof bound to
the exact commit and event root, gate identity with expiry and quorum, and a delivery/confirmation
loop. Each piece is small; together they are a system contract that is expensive to retrofit.

Source: `presentation/05-evidence.md`, `docs/reference/lifecycle/proof.md`.

## "What is actually built?"

The queue, the daemon, the API and SPA, the scheduler, the two gates, the proof, the verifier, the
openJiuwen and JiuwenSwarm adapters, delivery and confirmation. The Orbit MCP tools exist on the
Works side; Orbit calling Works and Orbit as a build adapter are proposed. The deck must mark the
difference.

Source: `presentation/05-evidence.md`, `docs/design/strategy/positioning.md`.

## "Why now?"

Agents are good enough to produce changes, and the bottleneck has moved to review and proof. The
tools that make a change provable are now the constraint on scaling agent work. That is the gap
Works fills.

Source: `README.md`, `docs/archive/reviews/review-4-factories.md`.
