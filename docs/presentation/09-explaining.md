# Explaining the product

The confusion is not about features. It is about layers. People know a harness when they see one;
they do not yet have a word for the product above it.

## The one picture

```
Models        Claude, GPT, DeepSeek, ...
Harnesses     openJiuwen, Claude Code, Codex, JiuwenSwarm
Hosts         Orbit (rooms), Works (change lifecycle)
People        the two decisions
```

A harness runs a turn. A host organises work above turns. People make the decisions that need
judgement.

## What a harness is

A harness is the thing that takes a task, calls tools, talks to a model and returns a result. It can
have a leader, subagents, a planner, tool approvals and its own memory. That is its inside.

The contract Works cares about is small:

```
propose(task, worktree) -> patch + transcript
challenge(patch, worktree) -> verdict
```

If a harness can answer those two calls, Works can use it. It does not matter whether the answer came
from one agent, a leader with five subagents, or a swarm.

## Black box vs white box

This is the distinction people are missing.

| View | What you care about | Examples |
|---|---|---|
| **White box** | How the work is split: leader, subagents, prompts, tools, approvals | JiuwenSwarm, Claude Code subagents, Codex |
| **Black box** | The contract: here is the task, here is the patch, here is the verdict | Works, Orbit, parallel agent runners |

Both are legitimate. A white-box platform optimises the build. A black-box host can choose any
harness, compare them, replace one with another and still own the same lifecycle.

JiuwenSwarm's leader and subagents are **inside the build**. They answer "how do we split and build
this task?". They do not answer "who is in the room?", "what was agreed?" or "is the change proven?".

## What Orbit is

Orbit is the horizontal app in this family. Its unit is a **room and a task**: rooms, connectors,
shared memory, routing, agent runtimes, approvals inside a conversation. It is deliberately generic —
sales, support, research and code in one product.

It can run harnesses and agents inside a room. It can also implement its own runtime protocol; it is
closer to the harness layer than Works is. But it is not the acceptance layer for a software change.

## Why Orbit if Swarm has leader and subagents?

Because they answer different questions:

| Product | Question | Unit |
|---|---|---|
| Orbit | Who is working with whom, about what? | a room |
| Swarm | How should the work be split and built? | a build |
| Works | How is the change proven and who signs it? | one change |

A leader inside Swarm cannot replace a room. A room cannot replace an independent inspection. An
inspection cannot replace the team that builds.

**Building-site analogy:**

- Orbit is the site office: people, decisions, coordination.
- Swarm is the construction team: a leader, sub-crews, the build.
- Works is the inspection and sign-off: independent check, proof, signatures.

The fact that the construction team has a foreman does not remove the site office or the inspector.
Nobody confuses these three on a building site. With agents they get confused because all three look
like AI.

## Why Works if Orbit exists?

They serve different purposes. Orbit optimises **coordination**; Works optimises **trust**.

Technically, you could add the lifecycle to Orbit. But then every room would inherit per-language
check contracts, worktree lifecycle, evidence hashes, commit binding, release gates and delivery
semantics — or Works would have to weaken them to stay generic. If you merge them, **Orbit stops
being generic and Works stops being strict**.

The integration is three narrow contracts, not a merge:

1. a room signal becomes a task;
2. Orbit can run a build turn for Works;
3. "fix and prove" is a tool that returns the proof and release state to the room.

Two products, one front door.

## Why not Jira or Jenkins?

Because they are workflow and tool runners, not agent lifecycles. Adding pipeline steps gives you
automation, not acceptance.

What a pipeline step does not know:

- whether the failure was reproduced on the current base commit;
- which plan a person approved, and which checks will judge the change;
- whether the builder edited the tests that judge it;
- whether the verifier was independent of the builder;
- whether the diff, the checks, the verdict and the event root belong to the same commit;
- who signed the release, with what identity, expiry and quorum;
- whether the reporter confirmed the real result.

You can build all of that inside Jenkins or Jira. Then Jenkins or Jira becomes an agent factory.
That is a different product, not a plugin.

**Analogies:**

- Jenkins is the robot that runs commands; Works is the inspector who signs the building. Teaching the
  robot to hold a pen does not make it an inspector.
- CI is a smoke detector; Works is the fire-inspection certificate. You want both.
- Jira tracks the ticket; it does not prove the change.

Works integrates with them: intake from Jira, CI commands as checks, delivery to GitHub or GitLab.
It sits above the agent and below the human decision.

## Products that use a harness as a black box

The category is real; the names change. Verify current names before putting them on a slide.

| Product / category | How it treats the harness |
|---|---|
| **OpenAI Performance Factory** (internal) | A task service and dispatch loop around Codex turns; the coding agent is the builder |
| **Alex Greenshpun's Outsourcerer / Total Recall** | An orchestrator and scheduler over agents; work is split outside the agent |
| **Parallel agent runners** (Conductor, Crystal, Claude Squad, Vibe Kanban) | Run many Claude Code or Codex sessions in parallel worktrees; each session is a black box |
| **Zed with Agent Client Protocol** | The editor hosts external agents as black boxes |
| **Orbit** | A horizontal room that can run harnesses and agents inside the work |
| **Works** | A vertical lifecycle that uses openJiuwen or JiuwenSwarm as the builder |

GitHub Copilot Workspace is a useful UX analog — a workspace above an agent — but it is not
harness-agnostic in the same way.

## One-liners for the meeting

- "A harness runs a turn. A host organises work. Works proves a change."
- "A leader inside the team cannot sign the inspection."
- "Swarm is capacity; Works is acceptance."
- "Orbit is the room; Works is the control plane for the change."
- "Jenkins runs the commands; Works signs the building."
- "A patch is an input to a proof, not a proof."
- "If you merge them, Orbit stops being generic and Works stops being strict."

## What not to claim

- Works does not replace the harness, Jira, Jenkins or Orbit.
- JiuwenSwarm is not a patch library; it is a multi-agent build platform.
- Orbit is not a worse Works; it is a different product with a different unit of work.
- Competitors can build a lifecycle; the argument is that doing so changes their product.
