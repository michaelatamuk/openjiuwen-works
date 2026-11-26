# Reporter loop (after release)

A released fix is not the end of the report. If the reporter says it still fails, the task can be
reopened instead of starting from zero.

## What is accepted

- A GitHub `issue_comment` delivery on the original issue (or on its pull request) with
  `action: created`. Signed with the same HMAC as every other delivery, rate-limited per source.
- A local `works retry <task-id> --note "..."`.
- Nothing else: there is no free-form chat, no email parsing and no Jira comment webhook yet.

## How the task is found

The comment is matched to a task by the issue reference (`owner/repo#number`) or by the issue URL
stored in the task's source links. If neither matches, the delivery is accepted with
`reason: no_task` and nothing is changed. The loop never guesses.

## What happens

1. A `reporter.replied` event records the text, author, source, URL, whether the report is closed,
   and the previous run and proof (`previous_run`, `previous_proof`).
2. A **released** task moves back to `queued`, with the transition reason `reporter_replied`. The
   scheduler still decides when it starts, under the same budget, labels and gates.
3. The planner receives the last three reporter notes as part of its bounded source text, next to
   the original title and reproduction hint. It does not see the whole comment thread.
4. A task that is not released is not reopened. A closed issue or pull request is recorded but not
   reopened; the event says so.

## Limits and refusals

| Case | Result |
|---|---|
| Same comment delivered twice (same delivery id, or same `event_id`) | `duplicate`, one event |
| Bot author (`type: Bot`, or a `[bot]` login) | `bot`, ignored |
| More than 3 replies in 24 hours | `limit`, recorded and refused |
| Task is not `released` | `not_released`, recorded |
| Issue or pull request is closed | `closed`, recorded, still released |
| No matching task | `no_task`, nothing written |
| Empty comment body | `empty` |

## Where it is visible

- The task thread shows a **Reported again** note with the author and the previous run.
- The Story card shows the same note above the route, with the previous proof one click away.
- `works task trace <id>` shows the event; `works retry` prints the outcome.

## Not built

- A Jira or Linear comment webhook.
- Writing back to the reporter beyond the existing delivery comment.
- Reopening a merged pull request automatically.
