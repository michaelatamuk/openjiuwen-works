# LAIX decision layer

LAIX is the optional decision layer between a plan and its execution. It answers one question for a
gate: given the recorded evidence, the budget and what needs approval, should the factory `wait`,
`observe`, `guide`, `ask`, `act`, `verify` or `escalate`? Works keeps the queue, state machine,
policy, verifier, ledger and proof.

**Status: adapter implemented, runtime not active.** `DecisionPort`, `DeterministicGate`,
`ShadowGate`, `LaixGate` and `works decision replay` exist and are tested with a fake LAIX module;
`WORKS_DECISION` defaults to `off`. The deterministic gate is what runs today. The pinned
`laix==0.18.0` cannot be a normal extra yet: the `laix` name on PyPI is an unrelated `0.0.0`
placeholder, so T2.14 must install the local LAIX checkout or publish the real package first.

## Boundary

| LAIX decides | Works enforces |
|---|---|
| `act / ask / wait / verify / escalate` at the plan and release gates | Path deny, budgets, state transitions |
| Which waiting decision deserves attention first | Timers, wake events, deadlines, defaults |
| Whether an approval is required | Approval bound to a commit and re-checked at publish |

LAIX cannot open a gate, admit a denied path, skip a deterministic node, replace the verifier or
write state. Path deny runs before the decision; the verifier's verdict runs after it. A missing,
invalid or timed-out decision falls back to the deterministic rule — the system fails closed.

## Event and proof

`Decision.to_dict()` is stored whole as a `decision.made` event and rendered as the **Decision**
section of the proof:

```
decision_id  DEC-…
trace_id     TRC-…
verb         act
reason_code  policy_rule
confidence   0.99
approval     required
alternatives ask, wait
```

Code branches on `reason_code`, never on `rationale`.

## Rollout

1. **Shadow** — LAIX computes, Works executes the deterministic gate; every difference is recorded
   and counted. No transition changes.
2. **Opt-in** — plan and release only, after the T2.14 replay of 20 historical cases shows no case
   where LAIX allows what policy or the verifier refuses.
3. **Attention** — `AttentionScheduler` ranks waiting tasks and gate requests under an explicit
   human-attention budget (`works attention` and the GUI).
4. **Commitments** — M3: `CommitmentGraph` carries `approved commit`, `CI green` and `return to the
   issue`; a hard violation becomes `verify` or `ask`.

`WORKS_DECISION=off | shadow | laix` selects the mode; `off` is the default.

## Inputs

`GateContext` is built from recorded evidence only: the reproduction result, plan spec and scenario
ids, verifier verdict, policy result, diff and touched paths, budget left, deadline and open
commitments. Agent-supplied urgency or free-form prose is never an input (D11, D13).

## What is not used

The LAIX app kit — execution, proposal store, delivery — stays out. Works is the host and already
owns those. LAIX is not a verifier: it decides whether to act, ask or verify; it does not prove the
patch.

## Known limits in 0.18.0

- Pre-1.0 (schema 0.8.0), external validation pending: pin `laix==0.18.0` behind `DecisionPort`.
- The default action policy returns `reason_code=policy_rule` for every path. Richer codes need a
  Works policy.
- `Decision.reversible` is not propagated from the chosen option in the default action policy; do
  not use it as a release gate input without a wrapper.
- The default policy returns `wait` unless urgency and uncertainty are supplied. Works derives them
  from evidence, never from the agent.

## Try it locally

```bash
pip install -e C:\Workspace\laix\packages\python\laix
python -c "from laix import decide; print(decide)"
```

The package has no dependencies and supports Python 3.11+.
