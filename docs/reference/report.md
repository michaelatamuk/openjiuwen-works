# Report

```bash
works report [--days 30] [--json]
```

A local, read-only summary of the queue and its history. No model, no network, no new storage: it
reads the same task events, run records and evidence the rest of the product already keeps.

## What it counts

| number | definition |
|---|---|
| Tasks | tasks created inside the window, grouped by state |
| Released | tasks that reached `released` |
| Runs | run records for those tasks |
| Total USD | latest evidence record per task, summed |
| Per released change | the same cost divided by released tasks |
| Time to release | first approved release minus the task's creation time; median and p90 over released tasks |
| Gates | approved / changes requested / rejected, per gate |
| Reopens | `reporter.replied` events that actually reopened a task |
| CVE | tasks whose source channel is `cve`, and how many were released |
| Escapes / rework | `escape.detected` and `rework.detected` events |
| Stops | run records by `stop_reason` |

## What it deliberately does not do

- No per-person productivity: the report measures changes, not people.
- No price or schedule forecast; those live in estimates and the scheduler.
- No cloud, no telemetry, no upload. The numbers stay in `~/.works`.
- A task that ran several times contributes only its latest run to cost; timing uses the first
  approved release. Both choices keep the number honest and are stated here rather than hidden.

## Reading it

An empty home prints zeros and "not enough data" for the timing. That is the correct answer for a new
install, not a bug.

```text
Works report · last 30 days · 2026-11-26
Tasks 12: released 7, proved 2, blocked 3
Runs 9 · $4.10 total · $0.59 per released change
Time to release: median 3 h 10 min · p90 9 h 00 min (7 change(s))
Gates: plan 9/2/1 · release 7/0/0 (approved/changes/rejected)
Reopens 1 · CVE 3 (2 released) · escapes 0 · rework 1
Stops: completed 7, tests_failed 1
```
