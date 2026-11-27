# Production feedback

```bash
works monitor --days 30
works monitor --days 7 --dry-run --json
```

Re-runs the confirmation target of released changes and opens a task when a change that passed
stops passing.

## Baseline

When a change is released, `confirmation.json` records the target (HTTP URL, command or the plan's
scenario set), the result and the output hash. The first `monitor` run stores that as the baseline in
`~/.works/state/monitor/<task>.json`; later runs keep the baseline and record the latest result beside
it.

A **drift** is a passing baseline and a failing re-check. A baseline that already failed is not a
drift: it belongs to the release decision.

## The drift task

- source kind `detector`, channel `drift`, ref `drift:<previous task>`;
- severity `S2`, labels `drift` and `previous:<id>`;
- reproduction hint: the target, the previous run, the previous proof fingerprint and the failure
  code;
- dedupe key `drift:<task>:<code>:<output hash>`.

The task goes through the queue, the scheduler, the budget and both gates. The monitor never
approves, releases or closes anything.

## Dry run

`--dry-run` re-checks and reports, but writes no confirmation, no monitor state and no task. It is the
safe way to see what the monitor would find.

## Not claimed

- Only the confirmation target is watched. OTel metrics, logs and traces are not ingested.
- No daemon-side polling yet; the command is explicit.
- A different response body with a passing status is not a drift.
- No automatic reopen, repair or close.
