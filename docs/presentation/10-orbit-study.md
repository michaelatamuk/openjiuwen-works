# Orbit study

> **Doc status:** active · **Owner:** Michael · **Last reviewed:** 2026-11-27

What was studied: `https://github.com/michaelatamuk/orbit`, cloned at
`/Users/mishka/PycharmProjects/openjiuwenothers/orbit`, commit `d53837a` (the repository has one
initial commit). Sources are file paths inside that checkout.

## Verdict in one line

Orbit is a local-first desktop workspace with **rooms, tasks, agent runtimes, git worktrees, coding
evidence, approvals, memory, schedules and delivery**. It is not just a room, and it already runs
coding agents. What it does not have is the **change acceptance contract** that Works builds around
the change: reproduce on the base commit, a plan gate, trusted-base checks, an independent verifier,
a proof bound to the commit and event root, a release gate, and code delivery/confirmation.

That is a narrower gap than "Orbit is only coordination", and a more honest one.

## What Orbit is, verified

### Shape

- Electron desktop shell + React workbench + local Python bridge. The bridge owns the workspace and
  talks to the shell over WebSocket. Source: `docs/orbit/architecture.md` §1–2.
- Local-first records in SQLite: one `OrbitStore` per workspace, records keyed by kind/id/revision,
  a source-events ledger, migrations, archive at the row cap. Source: `architecture.md` §2–3.
- Rooms/spaces, people, agents, linked chats, connectors, memory, generated views, schedules and
  triggers. Source: `README.md`, `core_functionalities.md`, `architecture.md` §3–9.

### Tasks

- A `Task` has objective, agent, runtime, routing decision, binding, status, cited sources and
  memories with revisions, artifacts, budget and origin. Source: `architecture.md` §3.
- `room.message` with `@agent` or `task.create` creates a task; the router chooses the agent and
  records why; `task.run` claims it. Each runtime has a run limit; tasks can queue. Source:
  `architecture.md` §4.
- A turn assembles a brief, executes with a time ceiling, stores the result, writes a `Run` record
  and a result message. Budget stop is `budget_state = "stopped"`. Source: `architecture.md` §4.
- `task.accept` closes a completed task. `task.cancel` cancels; `task.answer` resolves a question
  or an approval card bound to `prepared_action_hash`. Source: `architecture.md` §4.

### Harnesses as black boxes

- Every runtime implements one protocol: `availability`, `open`, `turn`, `interrupt`, `close`.
  Source: `services/agent_bridge/src/orbit_bridge/orbit_runtimes/base.py`.
- Runtimes: `claude` (Claude Agent SDK), `codex` (OpenAI Codex app-server), `swarm` (JiuwenSwarm
  gateway WebSocket), `jiuwen` (team backend), `human`, plus Orbit's own agent. Source:
  `architecture.md` §6, `orbit_runtimes/`.
- This is exactly the "black-box harness" idea: Orbit does not care how Claude or Codex splits work
  internally; it opens a session, streams a turn, handles tool approvals and closes.

### Coding gateway and worktrees

- The coding gateway runs Claude, Codex, Swarm and human turns. It allocates a private directory per
  conversation, mints a mandate per run, and turns each tool request into a `coding.tool` receipt on
  the harness gate. Source: `architecture.md` §6.
- A task with a `project_path` gets a separate git worktree from `HEAD`; an empty path gets a plain
  private directory. Worktree and provider-session locks; a parent can lend its worktree to a child.
  Source: `architecture.md` §6, `coding_providers.py`.
- This means Orbit does run builds, not just coordinate rooms.

### Coding evidence

- Each coding run snapshots the worktree as a git tree before and after, including untracked files.
  Source: `architecture.md` §6, `coding_providers.py`.
- The result includes a patch summary, test counts from the commands the runtime ran, and changed
  files with path, sha256, added/removed lines (up to 50); the test log becomes an artifact. Source:
  `architecture.md` §6, `coding_gateway.py`.
- This is real evidence, but it is **the runtime's own test run**, not an independent verifier and
  not a proof bound to a commit and event root.

### Approvals, grants and delivery

- Coding tool calls can become approval cards with `prepared_action_hash`; receipts can be
  indeterminate and block retries until reconciled. Source: `architecture.md` §6.
- Grants match task/action/provider/destination/identity; a delivery can be sent by a grant or needs
  a decision card. Delivery states include `pending`, `approved`, `sending`, `sent`, `failed`,
  `unknown`, `held`, `blocked`, `discarded`; receipts and `ReceiptUnknownError` exist. Source:
  `architecture.md` §8.
- A reply to a sent delivery can continue the task. Source: `architecture.md` §8.
- This is approval and delivery semantics for messages and actions, not a release gate for code.

### Other relevant capabilities

- Memory with source revisions, correction/invalidation, stale tasks and held drafts; source
  `EvidenceDrift` stops a run when a cited source changed. Source: `architecture.md` §7.
- Scheduler/triggers, run limits, budgets, cost/tokens per run. Source: `architecture.md` §4,
  `competitors.md`.
- MCP server with 35–36 tools for the task; ACP adapter so an editor can talk to Orbit's Home agent.
  Source: `architecture.md` §6, `docs/inbound-acp.md`.
- Cross-review: the docs mention `ORBIT_CROSS_REVIEW` and cross review up to 3 rounds; this is a
  partial independent-review feature, not the Works verifier. Source: `docs/orbit/competitors.md`,
  `orbit_review.py` (referenced there; verify implementation before quoting).
- Many live paths are unverified; the docs say so repeatedly. `competitors.md` calls the product a
  demo and lists "one live end-to-end run" as a gap. Treat live claims carefully.

## What Orbit does not have (relative to Works)

These are product-contract gaps, not insults. Each could be built.

| Works contract | Orbit status |
|---|---|
| Reproduce the failure on the current base commit before changing code | No reproduction stage found; tasks start from an objective/brief |
| Plan artefact + plan gate approving the checks before work | No plan artefact/plan gate found; tasks have objectives and tool/delivery approvals |
| Checks/scenarios read from the trusted base, not the worktree | No trusted-base check contract found |
| Independent verifier (separate runtime/provider/container, no builder transcript) | Cross-review exists; no independent verifier/check contract found |
| Proof bound to the diff, checks, verdict, artifacts and event root at one commit | Coding evidence exists (changed files, hashes, test log); no commit/event-root proof found |
| Release gate with identity, TTL and quorum for the exact commit | No code release gate found; delivery gate is for messages/actions |
| Code delivery to a forge and confirmation by the reporter | No code PR/merge/confirmation loop found in the product docs; delivery is messages/files. Verify before claiming |
| Two-gate lifecycle: plan and release | No plan/release gate pair found; task accept is a different decision |

## What this corrects in our story

1. **Do not say "Orbit is just a room."** It is a workspace with tasks, runtimes, worktrees, coding
   evidence, approvals, budgets and delivery.
2. **Do not say Orbit cannot build.** It can run Claude/Codex/Swarm turns in worktrees.
3. **Do not say Orbit has no evidence.** It has coding evidence with hashes and test logs. It does
   not have the Works proof binding.
4. **Do not say the gap is "everything".** The gap is the acceptance contract: reproduce, plan gate,
   trusted-base checks, independent verifier, commit-bound proof, release gate, code
   delivery/confirmation.
5. **The strategic argument still stands, but as a product choice.** Orbit could add the acceptance
   contract; then it would be a vertical software-delivery product, not the generic workspace. The
   integration through narrow contracts preserves both.

## The honest answer to "won't Orbit just do all this?"

It already does part of it: tasks, runtimes, worktrees, coding evidence, approvals, budgets,
delivery. To replace Works it would need the acceptance contract above. That is smaller than
"everything", but it is still the part that makes the result provable and releasable.

If Orbit adds it:

- every room inherits the strict contract, or
- one room type becomes a separate product inside Orbit, with its own team, roadmap, support and
  liability. That product is Works.

The site-office analogy becomes:

- Orbit is the project workspace: rooms, people, tasks, and it can call a crew.
- Swarm is the construction crew.
- Works is the turnkey delivery company: it runs the build through any crew, calls an independent
  inspector, binds the acceptance act and hands over the result.

The workspace can hire the crew and the inspector; it then becomes the delivery company. That is a
different product.

## What to verify before the final deck

- Whether Orbit can open a PR or merge code, or only deliver messages/files. The docs read like the
  latter; confirm in `orbit_connectors/github.py` and delivery code.
- Whether `orbit_review.py` gives a genuinely independent review or a same-provider cross-review.
- Which live paths have actually run; `competitors.md` says many have not.
- Whether the coding evidence is ever bound to a commit/event root in a way comparable to Works.

## Sources

- `README.md`, `core_functionalities.md`
- `docs/orbit/architecture.md` §1–9
- `docs/orbit/agent-runner.md`
- `docs/inbound-acp.md`
- `docs/orbit/competitors.md`
- `docs/orbit/failure-modes.md`
- `services/agent_bridge/src/orbit_bridge/orbit_runtimes/base.py`
- `services/agent_bridge/src/orbit_bridge/coding_gateway.py`
- `services/agent_bridge/src/orbit_bridge/coding_providers.py`
