# Specialist verifiers

A flow can ask for reviewers by area, in addition to the independent challenger. A specialist runs
only when the change touches its paths.

## Configuration

In the flow file:

```yaml
review:
  mode: observe            # off | observe | enforce
  specialists:
    security: ["auth/", "crypto/", "payments/", "secrets/"]
    performance: ["src/hot/"]
    data: ["migrations/", "schema/"]
```

- `off` is the default: no specialist runs and nothing is paid.
- `observe` runs the reviewers, records their verdicts and never changes the outcome.
- `enforce` turns a block into a challenge block, with a reason that names the area and its concerns.

The areas are fixed: `security`, `performance`, `data`. Each needs a prompt in the flow's `prompts/`
directory (`security.md`, `performance.md`, `data.md`), registered in `flows/prompts.lock.json`. An
unknown area, or a mode without any specialist, is a configuration error.

## What a specialist sees

The same change as the challenger, plus its slice:

```python
ReviewRequest(area="security", focus=["src/auth/login.py"], mode="enforce")
```

The prompt receives `$worktree`, `$ref`, `$title`, `$area` and `$focus`. The reviewer may read and run
the repository but may not edit or commit. It returns the same JSON contract as the challenger:
`{"allow": bool, "reason": str, "concerns": [str]}`.

## What the proof records

- `specialists.json` in the run directory: one object per reviewer.
- `Evidence.specialists`: area, allow, reason, concerns, model, provider, prompt hash, tokens and USD.
- `evidence.md` section **Specialist reviews** and a line in the plain-language summary.
- One `specialist.reviewed` event per reviewer, so the thread shows who looked at what.
- Cost in `verifier_tokens/usd` and in `model_calls` as `review:<area>`.

The list is bound into `proof_sha256`. Proofs written before M27 have no list and keep their hash.

## Harness support

`LiveHarness` (openJiuwen) and the fake harness support reviews. JiuwenSwarm does not: enabling
specialists with it is a configuration error rather than a silently generic challenge.

## Not claimed

- No debate or cross-review between specialists.
- No repair driven by a concern; the builder still gets a normal retry decision.
- No tool access beyond the challenger's worktree.
