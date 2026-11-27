# M27 — specialist verifiers (design)

> **Doc status:** archived · **Owner:** Michael · **Last reviewed:** 2026-11-26

Status: complete (27.1–27.5).

## Why

The product's claim is that a change is checked by someone who did not write it. M15 already added one
independent challenger. The research behind the recommendations says a single generalist reviewer is
not enough: security, performance and data regressions are different failure modes, and one prompt
asked to look for all of them finds fewer of each.

M27 lets a flow name specialist reviewers and the paths they care about. The change is still checked
by the same run, the verdict is still one decision, and the proof now records who looked at what.

## What already exists

| piece | where |
|---|---|
| Independent challenger with its own prompt and credential | `supervisor/verification.py`, `flows/*/prompts/challenge.md` |
| Harness contract `challenge(request, proposal)` | `adapters/harness/base.py` |
| Prompt files registered with owner and hash | `flows/prompts.lock.json`, `scripts/check_prompts.py` |
| Evidence sections and hash binding | `domain/evidence/` |

M27 adds a review request to the same contract, not a second pipeline.

## Decision

- **Configuration is per flow and off by default.**

  ```yaml
  review:
    mode: observe            # off | observe | enforce
    specialists:
      security: ["auth/", "crypto/", "payments/", "secrets/"]
      performance: ["src/hot/"]
      data: ["migrations/", "schema/"]
  ```

  An unknown area is a config error. A mode other than `off` without a specialist is a config error.

- **A specialist runs only when the change touches its paths.** Selection is a pure function over the
  proposal's touched paths; no match means no call and no cost.

- **The areas are fixed: `security`, `performance`, `data`.** Each has a prompt in the flow directory
  (`flows/fix-issue/prompts/security.md`, `performance.md`, `data.md`), registered like every other
  prompt. A flow can change the paths, not invent a persona with no prompt.

- **`observe` records, `enforce` decides.** In observe mode a block is written to the proof and the
  thread but does not change the challenge. In enforce mode a specialist block turns the challenge into
  a block with a reason that names the area and its concerns.

- **Each specialist is one harness turn.** It receives the same worktree and proposal through
  `ReviewRequest(area, focus, mode)`, gets its own system prompt and prompt hash, and its model, provider,
  tokens and USD are recorded in `specialists.json` and in `Evidence.specialists`.

- **The harness must say it supports reviews.** `LiveHarness` and the fake harness do; JiuwenSwarm does
  not. Enabling specialists with a harness that cannot run them is a configuration error, never a silent
  generic challenge.

## Evidence

- `Evidence.specialists` is a list of `SpecialistReview`; written before `bind()`, so it is covered by
  `proof_sha256`.
- Old proofs have no list; `bind()` excludes the field when empty, so their hash is unchanged.
- `evidence.md` gains **Specialist reviews**; the summary says `Specialist reviews: security block,
  performance allow.`; the UI shows a card and the thread shows one message per review.
- Cost lands in `verifier_tokens/usd` and in `model_calls` as `review:<area>`.

## Limits

- No debate between specialists, no cross-review and no automatic repair from a concern.
- No new tool access: a specialist reads the same worktree as the challenger and may not edit it.
- No per-specialist provider split beyond what the harness already supports.
- Enforce mode is opt-in; the default flow behaves exactly as before and pays nothing.

## Acceptance

| case | test |
|---|---|
| off selects nothing; paths select the right areas | `test_specialists.py` |
| observe records a block without changing the challenge | `test_specialists.py` |
| enforce lets a block fail the challenge | `test_specialists.py` |
| a harness without reviews is a config error | `test_specialists.py` |
| unknown area / mode without a specialist | `test_specialists.py` |
| evidence renders, summarises and binds the reviews; old hash unchanged | `test_specialists.py` |
| fake harness returns a deterministic specialist verdict | `test_specialists.py`, conformance |
| the UI shows the reviews | `Evidence.test.tsx` |

## Work breakdown

| item | days |
|---|---|
| 27.1 review config, selection and models | 0.7 |
| 27.2 harness review request and prompts | 1.0 |
| 27.3 verification merge, events and cost | 0.8 |
| 27.4 evidence, summary and UI | 0.7 |
| 27.5 docs, registry and tests | 0.8 |
| **total** | **4 (~5 with contingency)** |
