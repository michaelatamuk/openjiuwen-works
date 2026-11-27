# Confirm (stage 10)

Delivery says the branch and request exist; confirmation says the released commit still behaves.

## Targets

One explicit target, never implicit:

- `url` with optional `expect_status` and `expect_text`, and optional `expect_commit`;
- `command` run in a fresh worktree at the released commit;
- a Playwright preview script;
- otherwise the plan's scenario set.

"No target and no scenario set" is a `config_error`, not a pass.

## Binding and codes

`expect_commit` checks that the response names the released commit (short hash); a mismatch is
`wrong_commit`. Other codes: `target_unreachable`, `wrong_status`, `content_mismatch`,
`command_failed`, `check_failed`, and `unstable` when a retry changed the result.

## Retries

`attempts` (1–3) retries transient failures (unreachable, 5xx) with a short pause. If a later attempt
passes, the confirmation is recorded with `unstable: true` and the code `unstable`; it is not a silent
green.

## Deployment link

If `deployment.json` exists, its status is recorded on the confirmation, so a confirmation of a failed
deploy is visible instead of being mixed with a local check.

## Source report

On success Works can leave one marker comment on the source report; closing the issue is opt-in
(`close_issue`) and only after a passing confirmation. Repeating confirmation is idempotent and adds no
duplicate comment.

## Evidence and history

Every confirmation is a `confirmation.finished` event with commit, target, code, exit, duration,
output hash, screenshots and notes; `confirmation.json` keeps the latest record and the task detail
exposes recent history. A failed confirmation stays beside the proof; it does not rewrite it.
