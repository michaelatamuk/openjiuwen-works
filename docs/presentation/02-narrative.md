# Narrative

A 12-slide arc. Each slide has one job. The deck is a story about a category, not a feature tour.

## 1. Title

**Say:** "One signal in. A released fix out. Two human decisions."

Works is a local software factory. It is not an agent, a harness or a chat product. It runs one
change from signal to confirmation: it can use any harness as the builder, then verifies the result
and makes it provable and signed.

**Visual:** `../assets/ui/banner.svg` (or the dark variant).
**Source:** `README.md`.

## 2. The bottleneck

**Say:** "Writing code is no longer the bottleneck. Waiting is."

A fix spends its life in queues: for triage, for an agent's answer, for a reviewer, for proof. Agents
increase the amount of work that reaches review; they do not increase the number of people who can
approve it.

**Visual:** `../assets/ui/the-point.svg`.
**Source:** `README.md`, `docs/start/concepts.md`.

## 3. What Works does

**Say:** "Ten stages, two human gates. Everything between the two decisions is automatic and
recorded."

Signal → reproduce → plan → **plan gate** → build → check → proof → **release gate** → deliver →
confirm.

Works runs the build through a harness; the builder can be openJiuwen, JiuwenSwarm or an Orbit room.
The lifecycle stays with Works.

**Visual:** `assets/deck/software-factory-flow.svg`.
**Source:** `docs/start/concepts.md`, `docs/design/architecture.md`.

## 4. The product

**Say:** "The report, the route, the checks and the next step are in one place; the proof is one
click away."

Show the queue, one task's story, the proof page and the two decisions. The product is a window over
one home, not a chat.

**Visual:** `../assets/ui/story.png`.
**Source:** `README.md`, `docs/guides/workflow/ui.md`.

## 5. The proof is the product

**Say:** "A test report says the pipeline ran. A proof says what was checked, what was not, and binds
all of it to the exact commit."

The proof binds the diff, the artifacts, the event root and the page fingerprint. The checks come
from the base commit, so the change cannot rewrite the tests that judge it. `works proof verify`
recomputes it.

**Visual:** new diagram needed — **proof binding**. Use the existing flow as a placeholder until it
is drawn.
**Source:** `docs/reference/lifecycle/proof.md`, `docs/reference/lifecycle/gates.md`.

## 6. Three products, three questions

**Say:** "Orbit, a Swarm leader and Works are not three versions of one product. They answer three
different questions."

- Orbit: who, with whom, about what? They agree.
- Swarm: how should the work be split? They build.
- Works: how is the change delivered and proven? They accept the result.

Works also runs the build; the builder can be openJiuwen, JiuwenSwarm or an Orbit room. The question
is not who builds; it is what Works owns around the build.

**Visual:** `assets/deck/why-works/01-three-products.svg` and `assets/deck/why-works/02-three-questions.svg`.
**Source:** `docs/presentation/03-works-vs.md`, `docs/design/strategy/positioning.md`.

## 7. Three kinds of done

**Say:** "Agreed is not built. Built is not proven."

Only the third step can be shown to a customer, an auditor or a manager. A demo becomes a process
someone stands behind.

**Visual:** `assets/deck/why-works/04-three-done.svg`.
**Source:** `assets/deck/why-works/04-three-done.svg`.

## 8. Separation of roles

**Say:** "A leader cannot sign off their own work."

The leader owns the work. Someone outside the team owns the proof. Works can hire the team; it owns
the delivery and the proof.

**Visual:** `assets/deck/why-works/05-separation.svg`.
**Source:** `docs/design/adrs/005-verifier-independence.md`,
`docs/reference/lifecycle/gates.md`.

## 9. Two signatures

**Say:** "Two signatures on one case. Without the first we build the wrong thing. Without the second
we ship what was never proven."

- Plan gate: approve the checks before work.
- Release gate: approve the exact commit and its proof.

**Visual:** `assets/deck/why-works/06-two-signatures.svg`.
**Source:** `docs/reference/lifecycle/gates.md`.

## 10. Why pay for trust

**Say:** "Capacity does not scale without trust."

Swarm adds build capacity. Orbit adds coordination. Works delivers the change and owns the proof:
work that can be shipped. A demo becomes a process someone stands behind.

**Visual:** `assets/deck/why-works/07-why-pay.svg`.
**Source:** `assets/deck/why-works/07-why-pay.svg`.

## 11. How it compares

**Say:** "A harness runs a turn. A horizontal app organises work. An agent factory owns a ticket.
Works owns one change from signal to confirmation."

Use the category matrix: unit of work, what it owns, where it stops. Then the three direct
comparisons: openJiuwen, JiuwenSwarm, Orbit.

**Visual:** new comparison table; the current `positioning-two-products.svg` can support the Orbit
part.
**Source:** `docs/presentation/03-comparisons.md`, `docs/presentation/03-works-vs.md`.

## 12. Why not just add modules?

**Say:** "The module argument fails on ownership, not on code volume."

To add it to a harness, you add a queue, a state machine, worktrees, policy, a verifier, an evidence
schema, gate identity, delivery and confirmation. The harness stops being a harness. The same is true
for Orbit: it stops being generic. The same is true for a tracker or CI: they become an agent
factory.

**Visual:** new diagram needed — **not a plugin**. A box labelled "X" with the lifecycle modules
pulling it into a different product.
**Source:** `docs/presentation/03-comparisons.md`.

## 13. Evidence and what is built

**Say:** "This is not a slideware lifecycle. The queue, the gates, the proof, the verifier and the
daemon exist; the deck marks what is proposed."

Show the architecture and the tests. Be explicit about built vs proposed.

**Visual:** `../assets/ui/built-on-openjiuwen.svg` plus a built/proposed table.
**Source:** `docs/design/architecture.md`, `docs/presentation/05-evidence.md`.

## 14. The ask

**Say:** "Give us one real repository and one real class of change. We will show the two gates and the
proof on your code."

Ask for a demo or a pilot. End on the one line: harnesses run a turn, Orbit organises work, Works
proves a change.

**Visual:** banner or mascot.
**Source:** `README.md`.
