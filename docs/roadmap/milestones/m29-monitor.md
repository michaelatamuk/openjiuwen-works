# M29 — production feedback (design)

Status: complete (29.1–29.4).

## Why

A released change is a claim until something checks it again. Confirmation already re-runs the target
at the delivered commit; what was missing is the loop: remember the passing result, check again later,
and open a task when the result stops holding.

## Decision

**The baseline is the confirmation recorded at release.** It already names the target (HTTP URL,
command or the plan's scenario set), the output hash and the result. The monitor re-runs the same
target at the same delivered commit; it does not invent a new check.

**A drift is pass → fail.** A baseline that was already failing is not a drift; it is the state at
release and belongs to the release decision. A failed re-check after a passing baseline creates one
task with severity S2, the previous task, run and proof in its reproduction hint, and a dedupe key
that includes the failure code and the output hash. The same broken production does not create a task
every time the monitor runs.

**Explicit, local, read-mostly.** `works monitor` is a command, not a daemon loop yet. It re-runs the
stored target for released tasks in the window, keeps its state in
`~/.works/state/monitor/<task>.json`, and never approves, releases or closes anything. The new task
goes through the normal queue and both gates.

**Dry run changes no record.** `--dry-run` re-checks and reports, but writes neither a confirmation
nor monitor state and creates no task. The underlying `confirm()` gained `record=False` for exactly
this case.

## What the drift task carries

- source kind `detector`, channel `drift`, ref `drift:<previous task>`;
- severity S2, labels `drift`, `previous:<id>`;
- the target, previous run, previous proof fingerprint and the failure code in the reproduction hint;
- a dedupe key `drift:<task>:<code>:<output hash>`.

## Limits

- Only the confirmation target is watched; OTel metrics, logs and traces are not ingested.
- No continuous daemon poller yet; the command is explicit.
- A pass → pass with a different body is not a drift; only the result matters.
- No automatic reopen, repair, release or close.

## Acceptance

| case | test |
|---|---|
| pass → fail creates one drift task | `test_monitor.py` |
| the same drift is not filed twice | `test_monitor.py` |
| pass → pass files nothing | `test_monitor.py` |
| a baseline that already failed is not a drift | `test_monitor.py` |
| dry run writes no task and no state | `test_monitor.py` |
| no confirmation and a broken re-check are skipped with a reason | `test_monitor.py` |
| the CLI reports JSON | `test_monitor.py` |
| `record=False` leaves the confirmation untouched | `test_confirm.py` |

## Work breakdown

| item | days |
|---|---|
| 29.1 baseline state and target reuse | 0.7 |
| 29.2 drift detection and task creation | 0.8 |
| 29.3 CLI, dry run and `record=False` | 0.6 |
| 29.4 docs and tests | 0.6 |
| **total** | **2.7 (~3 with contingency)** |
