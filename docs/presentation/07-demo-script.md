# Demo script

A 10-minute demo that does not need a model, a network or a paid provider.

## Before the room

```bash
uv sync --extra dev
python scripts/demo-ui.py
# open the path the script prints
uv run works --home /path/printed/by/demo ui
```

The demo home has five example tasks, including one waiting at the release gate. Keep a second
terminal ready with `uv run works status` and `uv run works proof verify <run-id>`.

Fallback: `docs/assets/ui/story.png` and the proof page screenshot. If the live demo
fails, switch to the images and keep talking; do not debug in front of the audience.

## The 10-minute path

### 1. The queue (1 min)

**Show:** the queue, the waiting reasons.

**Say:** "One queue, one job per project. Each row says why it is waiting: a free slot, a person's
decision, the day's budget or the machine being busy."

### 2. One task (2 min)

**Show:** open the task at the release gate; the Story tab.

**Say:** "This is one change from report to release. Reported, picked up, confirmed, fixed, checked,
delivered. The technical line is in Evidence; the story is the same data."

### 3. The plan gate (2 min)

**Show:** the plan, the checks, the approve/reject decision.

**Say:** "The first signature is the plan. A person approves the checks that will judge the change,
before any code is written. The approval is bound to the plan hash."

### 4. The proof (3 min)

**Show:** Evidence: diff, commands, verdict, risk, not tested, cost, model/provider, prompt hash.
Then run `works proof verify <run-id>`.

**Say:** "This is not a test report. It binds the diff, the checks, the verdict, the artifacts and the
event root to the exact commit. If anything changes, verify fails with the failing check named."

### 5. The release gate (1 min)

**Show:** the release packet, blockers, approve; then delivery and confirmation.

**Say:** "The second signature is the release. A person approves the exact commit and its proof.
Delivery waits for that decision; confirmation checks the real result."

### 6. The close (1 min)

**Say:** "Harnesses run a turn. Orbit organises work. Works delivers a proven change. Give us one repository
and one class of change, and we will show the two gates and the proof on your code."

## The 20-minute path

Add:

- The architecture slide: one daemon, queue, job pool, scheduler, verifier.
- Works vs openJiuwen / JiuwenSwarm / Orbit: one slide each, one minute each.
- The "why not add modules" matrix.
- A second task at the plan gate to show the difference between the two decisions.

## What not to do

- Do not demo a live model without a recorded fallback.
- Do not read raw logs or internal reason codes to a product audience.
- Do not show a proposed Orbit integration as built.
- Do not claim Works replaces the harness, the tracker or CI.
- Do not spend the demo on settings, installs or provider keys.

## Questions to ask the audience

- Which repository would you use for a pilot?
- Which class of change is repeated enough to be worth proving?
- Who signs the plan and who signs the release today?
- What would make you trust an agent's change enough to ship it?
