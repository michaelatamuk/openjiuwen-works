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
shared memory, routing, agents, tasks, worktrees, coding evidence and approvals. It is deliberately
generic — sales, support, research and code in one product.

It can run Claude Code, Codex, Jiuwen and JiuwenSwarm behind one runtime protocol. It is closer to a
coding workspace than a pure room. But it is not the acceptance contract for a software change.

Works also runs builds. It can use openJiuwen, JiuwenSwarm or an Orbit room as the builder. The
difference is not who builds; it is who owns the change contract and the proof.

## Why Orbit if Swarm has leader and subagents?

Because they answer different questions:

| Product | Question | Unit |
|---|---|---|
| Orbit | Who is working with whom, about what? | a room and a task |
| Swarm | How should the work be split and built? | a build |
| Works | How is the change delivered, proven and signed? | one change |

A leader inside Swarm cannot replace a room. A room cannot replace the acceptance contract. The
acceptance contract can use the team that builds; it cannot outsource the proof.

**Building-site analogy:**

- Orbit is the project workspace: rooms, people, tasks, and it can call a crew.
- Swarm is the construction crew: a leader, sub-crews, the build.
- Works is the turnkey delivery company: it plans the job, hires or uses the crew, calls the
  independent inspector, assembles the acceptance act, delivers the building and confirms it.

The fact that the crew has a foreman does not remove the workspace or the delivery company. The
delivery company can hire the crew; it cannot sign for the inspector. Nobody confuses these three on
a building site. With agents they get confused because all three look like AI.

## Why Works if Orbit exists?

They serve different purposes. Orbit optimises **coordination and task execution**; Works optimises
the **acceptance contract**.

Orbit already has tasks, worktrees, coding evidence and approvals. Works also runs builds; it can use
an Orbit room as a builder, just as it can use openJiuwen or JiuwenSwarm. The difference is not who
builds; it is who owns the change contract: reproduction, the plan gate, trusted-base checks, the
independent verifier, the proof binding, the release gate, code delivery and confirmation.

Technically, you could add the acceptance contract to Orbit. But then every room would inherit plan
gates, trusted-base checks, independent verification, commit-bound proof, release gates and code
delivery/confirmation — or Works would have to weaken them to stay generic. If you merge them,
**Orbit stops being generic and Works stops being strict**.

The integration is three narrow contracts, not a merge:

1. a room signal becomes a task;
2. Orbit can run a build turn for Works; Works can equally build through openJiuwen or Swarm, so the
   builder is interchangeable;
3. "fix and prove" is a tool that returns the proof and release state to the room.

Two products, one front door.

## "Won't Orbit just do all this?"

Technically, yes. There is no magic in the lifecycle; Orbit could add it. The question is what it
would have to become.

| Orbit already has | The acceptance contract adds | What Orbit becomes |
|---|---|---|
| rooms, people, tasks, queue, budgets, routing; Claude/Codex/Jiuwen/Swarm runtimes; worktrees; coding evidence; approvals, grants and a delivery gate; memory and schedules | reproduce-on-base; plan artefact + plan gate; trusted-base check contract; an independent verifier; a proof bound to the commit and event root; a release gate; code delivery and confirmation | a vertical software-delivery product, not a generic workspace |

There are only two ways to add it:

1. **Every room gets it.** Sales and support rooms inherit plan gates, checks and proof hashes. Orbit
   stops being generic.
2. **One special room type gets it.** That is a separate product inside Orbit, with its own team,
   roadmap, support and liability. That is Works.

The project workspace can hire the crew and the inspector, but then it is the delivery company. That
is a different business with a different buyer, failure mode and contract. It is not a feature of the
workspace.

If Orbit's strategy is to own software delivery, it can absorb Works. Then Works is redundant — but
Orbit is no longer the horizontal workspace product. That is a strategic choice, not a technical one.

## Why not Jira or Jenkins?

Because they are workflow and tool runners, not change lifecycles. Adding pipeline steps gives you
automation, not the change contract.

Works also runs builds; Jenkins can be a tool inside Works. The difference is what surrounds the
build:

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

- Jenkins is the robot that runs commands; Works is the delivery company that runs the project,
  hires the inspector and signs the result. Teaching the robot to hold a pen does not make it the
  delivery company.
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
| **Orbit** | A horizontal workspace with rooms, tasks, worktrees and coding evidence; runs Claude/Codex/Jiuwen/Swarm behind one runtime protocol |
| **Works** | A vertical change lifecycle that can use openJiuwen, JiuwenSwarm or an Orbit room as the builder |

GitHub Copilot Workspace is a useful UX analog — a workspace above an agent — but it is not
harness-agnostic in the same way.

## One-liners for the meeting

- "A harness runs a turn. A host organises work. Works delivers a proven change."
- "Works can hire any builder; it cannot outsource the proof."
- "A leader inside the team cannot sign the inspection; Works can hire the team and the inspector."
- "Swarm is a builder; Works is the change lifecycle that can use it and still owns the proof."
- "Orbit is the workspace; Works is the acceptance contract for one change."
- "Jenkins runs the commands; Works runs the change and signs the result."
- "A patch is an input to a proof, not a proof."
- "If you merge them, Orbit stops being generic and Works stops being strict."

## What not to claim

- Works does not replace the harness, Jira, Jenkins or Orbit.
- Works is not only an inspector: it runs the build through a harness, Swarm or an Orbit room, then
  verifies and proves the result.
- Orbit is not just a room: it runs tasks, worktrees and coding evidence. The difference is the
  acceptance contract.
- JiuwenSwarm is not a patch library; it is a multi-agent build platform.
- Orbit is not a worse Works; it is a different product with a different unit of work.
- Competitors can build a lifecycle; the argument is that doing so changes their product.
