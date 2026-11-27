# Works vs openJiuwen, JiuwenSwarm and Orbit

These are not three versions of Works. They are different layers with different units of work.
Works consumes the first two and composes with the third.

| Thing | Unit | Owns | Where it stops |
|---|---|---|---|
| **openJiuwen** | One agent turn | Model, tools, the harness loop | When the turn ends |
| **JiuwenSwarm** | A multi-agent build | Splitting work, leader/subagents, its own gateway and models | When the build returns |
| **Orbit** | A room and a task | People, coordination, shared memory, routing, agent runtimes | When the work is agreed or handed off |
| **Works** | One change | Reproduce, plan gate, build, check, proof, release gate, deliver, confirm | When the reporter confirms the fix |

## Works vs openJiuwen

**openJiuwen is the harness.** It exposes `HarnessProtocol` and provider harnesses — Claude Code,
DeepSeek Harness, Jiuwen native and Codex — inside the Works process. It runs a turn, calls tools and
returns a proposal.

**Works is the factory around the harness.** It owns the queue, reproduction, the plan and its gate,
the worktree, policy, the verifier, the proof, the release gate, delivery and confirmation. The
harness is the builder; the factory decides what to build, what will judge it, and whether it may
ship.

### What Works uses from openJiuwen

- `propose` for the builder turn; `challenge` for an independent review session.
- Provider selection (Claude Code, DSH, native, Codex) per run.
- The turn result for model, provider, tokens, USD and prompt hash.
- The planner harness, read-only, for assisted/deep plan modes.

### What openJiuwen does not do

- No durable queue or task state machine.
- No plan gate or release gate with identity, expiry and quorum.
- No independent verifier with a container boundary.
- No proof bound to the commit, the checks and the event root.
- No delivery or confirmation loop.

### The common confusion

> "Works is a harness." / "Works is openJiuwen."

No. Remove the harness and Works still has a product: queue, policy, gates, proof, delivery.
Remove the lifecycle and nothing is left. Works is not a model, an agent loop or a tool runtime.

### What is built

- The `propose`/`challenge` contract and the openJiuwen adapters (Claude Code, DSH, native, Codex).
- Live runs with a versioned builder prompt and a separate challenger session.
- A fake harness for deterministic CI.
- Recorded traces; a live model is never required for the test suite.

### What not to claim

- "openJiuwen is a commodity." It is essential; Works consumes it.
- "Works replaces the harness." It does not.
- "The harness is the product." A turn is not a change.

Sources: [`live-harness.md`](../guides/integrations/live-harness.md),
[`ADR-008`](../design/adrs/008-live-harness.md),
[`architecture.md`](../design/architecture.md).

## Works vs JiuwenSwarm

**JiuwenSwarm is an external multi-agent platform.** It carries its own runtime, gateway, A2A server,
tool approvals, model configuration and a pinned `openjiuwen`. It is a builder boundary, not a patch
library. Installing it inside the Works virtualenv would replace the builder and break the verifier.

**Works treats it as an external builder behind a contract.** The contract is
`works.swarm.v1`: Works writes a `request.json`, a separate process runs the Swarm entrypoint, and
the entrypoint writes `result.json` with either a patch and touched paths (`propose`) or a JSON
verdict (`challenge`).

### What Swarm owns

- Splitting the work across a leader and subagents.
- Its own gateway, models, tool approvals and runtime.
- Build capacity inside the disposable worktree.

### What Works owns

- The plan and the plan gate.
- Policy over touched paths.
- The verifier, the P0/P1 verdict and the proof.
- The release gate, delivery and confirmation.

### The boundary

- The worktree is the only shared path.
- The adapter may edit the worktree, like the live harness; policy runs afterwards.
- Works does not import JiuwenSwarm and does not inherit its dependency tree.
- The builder cannot open a gate or write the release packet.
- A builder that cannot run fails as a configuration error; there is no fake fallback.

### The common confusion

> "Swarm is the factory."

No. Swarm is a builder. A leader can split work and build, but a leader cannot sign off its own work.
The change lifecycle is outside the team; it can hire the team and still owns the proof.

### What is built

- `works.swarm.v1` adapter and `works swarm doctor`.
- `works run --swarm` with preflight and no fallback.
- The adapter is stdlib-only and tested with a fake CLI.
- A live run still needs the Swarm gateway/model configuration and an isolated venv; the live model
  is not part of CI.

Sources: [`swarm.md`](../guides/integrations/swarm.md),
[`live-harness.md`](../guides/integrations/live-harness.md),
[`ADR-010`](../design/adrs/010-factory-and-attention.md).

## Works vs Orbit

**Orbit is horizontal.** Its unit is a room and a task: rooms, connectors, shared memory, routing,
agent runtimes and approvals inside a conversation. It is deliberately generic — sales, support,
research and code in one product.

**Works is vertical.** Its unit is one change: reproduce, plan gate, build, check, proof, release
gate, deliver, confirm. It is deliberately narrow — software changes, one way.

They are both above harnesses. They are not above each other.

Works also runs builds. It can use openJiuwen, JiuwenSwarm or an Orbit room as the builder; the
independent inspector is a role inside Works, not the whole product. The difference is the change
contract: reproduction, the plan gate, the check contract, the proof binding, the release gate,
delivery and confirmation.

### What Orbit owns

- The room, the people and the conversation.
- Connectors, shared memory, routing and schedules.
- Agent runtimes: Claude Code, Codex, Jiuwen, JiuwenSwarm, human.
- Tasks, task queue, budgets, routing and bindings.
- Git worktrees and coding evidence (changed files, hashes, test log).
- Approval cards, grants, delivery gate, receipts and task acceptance.
- The front door for many kinds of work.

### What Orbit does not own

- Reproduction of the failure on the current base commit as a required stage.
- A plan artefact and a plan gate that approves the checks before work.
- A trusted-base check contract (checks and scenarios read from the base commit).
- An independent verifier separate from the builder.
- A proof bound to the diff, checks, verdict and event root at one commit.
- A release gate for code and a code delivery/confirmation loop.
- The two-gate lifecycle: plan and release.

Orbit has coding evidence, but it is the runtime's own test run and changed-file summary, not a proof
bound to the commit and the event root. It also has cross-review between agents; that is useful, but
it is not a separate verifier with a trusted-base check contract.

### How they compose

Three narrow contracts, not a merge:

1. **A room signal becomes a task.** Orbit sends the report through Works intake (`submit_signal`
   over MCP).
2. **Orbit can run the build turn.** Works treats Orbit like any build adapter; the patch returns to
   the same run for checks. Works can equally build through openJiuwen or JiuwenSwarm, so the builder
   is interchangeable.
3. **"Fix and prove" is a tool.** An agent in Orbit calls Works and gets the proof and release state
   back into the room (`evidence`, `release` over MCP).

### "Won't Orbit just do all this?"

Technically, yes. It would have to add the acceptance contract on top of what it already has.

| Orbit already has | The acceptance contract adds | What Orbit becomes |
|---|---|---|
| rooms, people, tasks, queue, budgets, routing; Claude/Codex/Jiuwen/Swarm runtimes; worktrees; coding evidence; approvals, grants and a delivery gate; memory and schedules | reproduce-on-base; plan artefact + plan gate; trusted-base check contract; an independent verifier; a proof bound to the commit and event root; a release gate; code delivery and confirmation | a vertical software-delivery product, not a generic workspace |

There are only two ways to add it:

1. **Every room gets it.** Sales and support rooms inherit plan gates, checks and proof hashes. Orbit
   stops being generic.
2. **One special room type gets it.** That is a separate product inside Orbit, with its own team,
   roadmap, support and liability. That is Works.

The project workspace can hire the crew and the inspector, but then it is the delivery company. That
is a different business, not a feature of the workspace.

### Why the merge fails

> "Orbit should absorb the factory."

A horizontal product would have to own the acceptance contract — reproduce-on-base, a plan gate,
trusted-base checks, an independent verifier, commit-bound proof, a release gate and code
delivery/confirmation — while keeping all of it generic for every room. It already has tasks,
worktrees and coding evidence; the missing piece is the part that makes the result provable and
releasable. If you merge them, **Orbit stops being generic and Works stops being strict**.

### What is built vs proposed

| Piece | State |
|---|---|
| Works harness contract (`propose`, `challenge`) and adapters | built |
| Works MCP tools: `submit_signal`, `list_tasks`, `task`, `evidence`, `release` | built |
| Works intake from GitHub, Jira, a monitor and a person | built |
| Orbit rooms, connectors, memory, routing, tasks, worktrees, coding evidence, approvals and runtimes | built, in Orbit |
| Orbit calling Works over MCP | proposed |
| Orbit as a Works build adapter | proposed |
| Works accepting a signal from an Orbit room | proposed |

Do not draw the proposed links as solid in public material.

### The common confusion

> "Orbit already runs Claude and Codex." — That is the build turn. Works can use that turn and still
> owns the proof. The proof is what happens after the patch.
>
> "Orbit already has tasks and evidence." — It has tasks and source evidence for a briefing. It does
> not bind a diff, checks, a verdict and a release to one hash.
>
> "Why not one product?" — One product would have to be both generic and strict at the same time.
> The MCP boundary gives one front door with two engines.

Sources: [`positioning.md`](../design/strategy/positioning.md),
[`architecture.md`](../design/architecture.md),
[`ADR-010`](../design/adrs/010-factory-and-attention.md).

## One picture

```
Orbit        who, with whom, about what?          they agree
Swarm        how should the work be split?        they build
Works        how is it delivered and proven?      they accept the result
```

The same agent can appear in all three. The products answer different questions.

- Agreed is not built.
- Built is not proven.
- A leader cannot sign off its own work.
- A patch is an input to a proof, not a proof.
- Works runs the build; the inspector is a role inside it, not the product.

## One-line answers for the meeting

- "Works is not a harness; it consumes one."
- "Swarm is a builder; Works is the change lifecycle that can use it and still owns the proof."
- "Orbit is the workspace; Works is the acceptance contract for one change."
- "Works runs builds; it can hire Orbit as one of the builders."
- "If you merge them, Orbit stops being generic and Works stops being strict."
- "A patch is an input to a proof, not a proof."

## What not to claim

- Works does not replace openJiuwen, JiuwenSwarm or Orbit.
- Proposed integrations are not built integrations.
- Competitors can build this; the argument is that doing so changes their product.
