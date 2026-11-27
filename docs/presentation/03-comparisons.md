# Comparisons

The three direct comparisons — Works vs openJiuwen, JiuwenSwarm and Orbit — are in
[03-works-vs.md](03-works-vs.md). This file is the wider category matrix and the "why not add
modules" argument.

Every comparison below is a category comparison, not a feature checklist. The point is not that the
others are bad; the point is that they answer a different question.

## The category matrix

| | Unit of work | What it owns | What it does not own | Where it stops |
|---|---|---|---|---|
| **Harness** (openJiuwen, Claude Code, Codex) | One turn | Model, tools, the agent loop | Queue, policy, proof, gates, delivery | When the turn ends |
| **Horizontal app** (Orbit) | A room and a task | People, chats, coordination, routing, shared memory | Per-language check contracts, proof binding, release semantics | When the work is agreed or handed off |
| **Agent factory** (Devin, Factory.ai, OpenHands) | A ticket or a task | Planning, execution, some review; usually cloud or self-hosted | Local-first ownership, open harness choice, two-gate proof binding as the product | At the vendor's boundary |
| **Tracker + CI** (Jira, GitHub Actions) | An issue and a check | Workflow state, build and test execution | The agent lifecycle, the plan/release decision, the proof | When CI is green |
| **Works** | One change | Reproduce, plan gate, build, check, proof, release gate, deliver, confirm | The model, the agent turn, deploy | When the reporter confirms the fix |

## The question each product answers

| Product | Question |
|---|---|
| Orbit | Who is working with whom, about what? |
| Swarm | How should the work be split and built? |
| Works | How is the change proven and who signs it? |
| A harness | What can one agent do in one turn? |
| A tracker + CI | Did the pipeline run? |

The same agent can appear in all of them. The products are not three versions of one thing; they are
three different jobs.

## "Why not just add these modules to X?"

The module argument sounds cheap because the pieces look small. They are not small once they have to
be true together.

| If you add it to… | What you actually have to add | Why it changes the product |
|---|---|---|
| **A harness** | Durable queue, state machine, worktrees, policy, independent verifier, evidence schema, gate identity and TTL, delivery and confirmation | The harness stops being a turn and becomes a factory. Its contract, latency and failure model change. |
| **Orbit** | Per-language check contracts, proof hashes, commit binding, release semantics, a queue with budgets | Orbit stops being generic. Every room would inherit a strict software lifecycle it does not need. |
| **An agent factory** | Local-first ownership, open harness choice, two human gates, a proof bound to the commit, a confirmation loop | It can be built, but it is a different product for a different buyer. The vendor's cloud and workflow are the product. |
| **A tracker + CI** | An agent runtime, a planner, a verifier, a proof, gate decisions, delivery markers | The tracker and CI become an agent factory. That is a new product, not a plugin. |

## Why the big vendors will not simply ship it

This is an argument, not a fact about any one roadmap. It should be tested in the meeting.

1. **Their unit is the turn or the ticket.** A proof-bound lifecycle adds states, waits and human
   decisions that slow the demo. It is not a natural upsell for a tool measured by turns.
2. **Their distribution is the model or the cloud.** Works is local-first and harness-agnostic. A
   vendor that owns the model or the cloud has little reason to make the harness interchangeable.
3. **Their buyer is different.** A coding-tool buyer asks "can it write the change?". A Works buyer
   asks "can I stand behind the change?". The second buyer needs evidence, not a faster autocomplete.
4. **The hard part is the contract, not the UI.** The proof must bind the diff, the checks, the
   verdict and the event root to one commit. Gate identity, expiry and quorum must be real. That is
   system work, not a settings page.
5. **A module would be a second product inside the first.** It would need its own queue, its own
   failure semantics and its own human gates. Companies can do it; they cannot do it without
   becoming a different product.

## Honest boundaries

- Works does not write the model or run the agent loop; it consumes a harness.
- Works does not deploy; release means merged and confirmed.
- Works is not a chat surface or a general-purpose assistant.
- Works is not multi-tenant or cloud-first; one home, one writable daemon.
- Orbit and Works can compose through narrow contracts; neither replaces the other.

## What not to claim

- "Competitors cannot build this." They can. The claim is that doing so changes their product.
- "Works is the only agent factory." It is not; it is the one that makes the proof and the two gates
  the product.
- "The harness is commodity." The harness is essential; Works is the layer above it.
