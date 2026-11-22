# Release, delivery and confirmation

Three separate acts, in order. None of them decides for a person.

```bash
works release <task-id>                 # read-only packet
works approve <task-id> --gate release  # gate 2: a person releases
works deliver <task-id> --provider none # commit the approved diff, push a branch
works confirm <task-id> --url https://app/health
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

## 4. Confirmation

`works confirm <task-id>` checks the delivered commit in a fresh worktree:

- `--url URL` → one HTTP check;
- `--command CMD` → one command (a JSON array is accepted for exact argv);
- otherwise the plan's scenario set is re-run.

The result is written to `runs/<run-id>/confirmation.json` and recorded as
`confirmation.finished`. A repeat returns the recorded result; `--force` runs again.

With `--tracker github|gitlab|jira`, the result is commented on the source issue; `--close` closes
a GitHub/GitLab issue or transitions a Jira issue to Done, but only when the confirmation passed.
All return calls are idempotent by run marker.

A desktop GUI needs a real driver. Without one, Works confirms CLI, HTTP and scenario targets and
says what it did; it does not claim a person clicked through the product.
