# Release, delivery and confirmation

Three separate acts, in order. None of them decides for a person.

```bash
works release <task-id>                 # read-only packet
works approve <task-id> --gate release  # gate 2: a person releases
works deliver <task-id> --provider none # commit the approved diff, push a branch
works deploy <task-id> --command "..."   # owner-approved command on the delivered commit
works confirm <task-id> --url https://app/health
works escapes                            # reverts, hotfixes, repeated sources
```

## 1. The packet

`works release` is the last read-only check. It binds:

- the latest finished run;
- the base commit;
- the proof SHA-256 (which covers the diff);
- the plan approval and whether it is bound to the same commit;
- the release approval, if one exists;
- blockers: task not proved, missing proof, verdict not allow, blocked independent review, missing
  gate, or an approval bound to another commit.

Exit code `0` means ready; `8` means blocked. A packet is not a release.

## 2. Gate 2

`works approve --gate release` opens the gate:

1. rebuilds the packet without requiring the release approval;
2. refuses while any other blocker remains;
3. moves `proved` (or a waiting state) through `releasing` to `released`;
4. records `gate.decided` with `gate=release`, the base commit, the proof SHA, the run and the time;
5. writes `runs/<run-id>/release.json`.

A repeat approval for the same commit returns the existing release; it never appends a second gate
event. Approving a different commit after a release is refused.

Gate 2 does **not** push, open a pull request or comment. That is delivery.

## 3. Delivery

`works deliver <task-id>` turns the approved diff into a commit and a branch:

- requires `released` and a ready packet;
- rebuilds the worktree from the approved diff if the original is gone;
- verifies the worktree diff hash against the proof before staging anything;
- refuses if the staged file list differs from the proof's file list;
- commits with `Works-Task`, `Works-Run`, `Works-Source` and `Works-Proof` trailers;
- creates `works/<task-id>` and pushes it to `origin`;
- `--provider github` or `--provider gitlab` also opens one pull/merge request;
- `--tracker github|gitlab|jira` returns one comment to the source issue, idempotent by run marker;
- `--dry-run` commits locally and stops.

A tracker and a forge are separate. `--provider github --tracker jira` opens a GitHub pull request
and comments on the Jira issue. With no `--tracker`, the tracker follows the provider; a source the
default tracker cannot read is skipped with a note.

A retry returns the existing `delivery.json` instead of a second commit, pull request or comment. A
dry run can be followed by a real delivery of the same commit.

Live output needs credentials and a real remote:

| Target | Variables |
|---|---|
| GitHub | `GITHUB_TOKEN`, a GitHub remote |
| GitLab | `GITLAB_TOKEN`, `GITLAB_URL` (default `https://gitlab.com`), a GitLab remote |
| Jira | `JIRA_URL`, `JIRA_EMAIL`, `JIRA_TOKEN` |

Tests use a local bare remote and fake forge/tracker transports.

## 3b. Deploy

`works deploy <task-id>` runs the deploy command for the exact commit that was delivered:

- requires `released` and a real `delivery.json` with a commit;
- refuses a dry-run delivery that was never pushed (unless `--dry-run` is used again);
- takes `--command` as an argv list, a JSON array or a quoted string, or reads `deploy:` from
  `.works/products.yaml`;
- runs from the task's repository with `WORKS_TASK_ID`, `WORKS_RUN_ID`, `WORKS_COMMIT`,
  `WORKS_ENVIRONMENT` and `WORKS_DEPLOY_DRY_RUN`;
- records `runs/<run-id>/deployment.json` and a `deploy.finished` event;
- is idempotent per run, commit and environment; `--force` repeats a successful deploy.

No shell is used. A failed command is recorded as `failed` and the CLI exits `8`. Merge, production
credentials and rollback stay human/operations concerns.

## 4. Confirmation

`works confirm <task-id>` checks the delivered commit in a fresh worktree:

- `--url URL` → one HTTP check;
- `--command CMD` → one command (a JSON array is accepted for exact argv);
- `--preview FILE` — a Playwright YAML script that drives the real user path;
- otherwise the plan's scenario set is re-run.

`--preview` needs the optional browser extra (`uv sync --extra preview`, then
`playwright install chromium`). The script has a `start_url` and an ordered list of `goto`, `click`,
`fill`, `expect_text`, `expect_visible`, `wait` and `screenshot` steps. Screenshots are written
under `runs/<run-id>/preview/` and listed in `confirmation.json`; a missing extra fails closed.

The result is written to `runs/<run-id>/confirmation.json` and recorded as
`confirmation.finished`. A repeat returns the recorded result; `--force` runs again.

With `--tracker github|gitlab|jira`, the result is commented on the source issue; `--close` closes
a GitHub/GitLab issue or transitions a Jira issue to Done, but only when the confirmation passed.
All return calls are idempotent by run marker.

A desktop GUI needs a real driver. CLI, HTTP and scenario targets work without one; `--preview`
supplies the browser driver instead of claiming a green result it did not observe.

## 5. Escapes and rework

`works escapes` derives quality signals from recorded history:

- a `Revert "..."` commit whose body reverts the delivered commit is a `revert` escape;
- a `hotfix` commit touching the same paths inside the release window is a `hotfix` escape;
- a later task with the same source reference is rework.

It writes `escapes.json`, records `escape.detected` / `rework.detected`, and `works metrics` reports
both counts. `--days` changes the window and `--dry-run` scans without writing. The first version
reads local git history; a remote main/CI feed can post the same findings later.
