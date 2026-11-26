# ADR 026 — Risk and the summary are evidence, never a gate

Status: accepted, 2026-11-26 (M23.1–M23.3 landed with tests).

## Context

M23 adds three things to the release gate: a risk tier built from more signals, a plain-language
summary of the proof, and a way for the reporter to reopen a released task. Each invites the same
shortcut:

- let the risk tier approve a low-risk change (or block a high-risk one) without a person;
- let a model write the summary, so the page sounds confident;
- let a replayed comment reopen a task and reuse the old approvals.

All three would weaken the only property that makes the proof worth reading: a named person, on a
device, decided twice, and the evidence they decided on cannot change afterwards.

## Decision

1. **The tier is recorded before `bind()`.** It is part of the evidence and therefore part of
   `proof_sha256`; editing it after approval breaks `works proof verify`.
2. **The tier can only route to a person.** A high tier names the owners the flow already declares
   and asks for the owner's approval at release. It never approves, bypasses or silently blocks a
   gate. A scheduler risk cap is separate, configured policy, not the tier acting on its own.
3. **No new model call.** The tier is deterministic from paths, churn and the flow's sensitive
   paths. The summary is a deterministic template over the evidence record: no model, no invented
   number, and a missing field is named as missing.
4. **The summary is bound, and old proofs are not rewritten.** New runs store the summary and its
   artifact hash before binding. Records written before M23 render the summary on read, are marked
   `derived`, and keep their original hash.
5. **Reopening returns to the queue, not to the previous approvals.** A reporter reply moves a
   released task to `queued`. The plan gate is bound to the plan hash and the release gate to the
   commit and proof, so neither old decision can be reused for the next run.
6. **A reply is context, not an instruction.** The planner sees the last three reporter notes next
   to the original report. It does not see the thread, and it cannot approve anything.

## Consequences

- A manager can read the page without reading a diff, and a reviewer can still audit every number.
- More risk signals mean more reasons on the page; they do not mean more automatic decisions.
- The owner rule now triggers for payments, crypto and key material even when a flow forgot to list
  them as high-risk paths. That is intentional; it can only add a person, never remove one.
- Reopened tasks pay for a fresh plan draft and a fresh run. The old proof stays on disk and remains
  verifiable; it is simply no longer the latest one.
- Tests must keep the refusal path explicit: a high tier still asks a person, a bot comment is
  ignored, and an old proof verifies byte-for-byte.

## Alternatives rejected

- **Auto-approve low risk.** The tier would become the approver, and the two-gate promise becomes a
  UI detail.
- **Block high risk automatically.** A local tool that refuses to let a person decide is a policy
  engine with no owner; the flow's owner rule is the right place for that.
- **A model-written summary.** It would add cost, variance and a second opinion about the same
  evidence, with no way to tell a fact from a plausible sentence.
- **Rewrite old proofs to add a summary.** It would invalidate every existing hash and destroy the
  only reason to keep the page.
- **Reopen straight into `plan_approved`.** It would reuse an approval for a plan the reporter has
  just contradicted.
