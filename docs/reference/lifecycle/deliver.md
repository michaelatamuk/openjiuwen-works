# Deliver (stage 9)

Delivery turns a released commit into a branch, a change request and one comment. It never merges and
never force-pushes.

## Preflight

Before any network write:

- the commit must descend from the approved base (`git merge-base --is-ancestor`);
- the proof must still match the delivered commit;
- a dry run stops here: branch and message are prepared, nothing is sent;
- a forge without a token is refused with `the forge has no token` and the attempt is recorded.

## Steps and journal

`delivery.json` is rewritten as the delivery advances:

| step | meaning |
|---|---|
| `commit` | the approved diff was committed on the branch |
| `branch` | the branch was moved to that commit |
| `preflight` | ancestry and proof checks passed |
| `push` | the branch reached the remote |
| `pull_request` | the change request exists (looked up by head/marker) |
| `comment` | one comment exists on the source report (looked up by marker) |

`completed` is set only after the last step. A record without it is a partial delivery: a retry
continues from the recorded commit and markers instead of treating the journal as finished. A failure
sets `failure` and a failed step, which the Release page shows.

## Change request content

The body carries the task, run, commit, proof fingerprint, verdict, risk, the passed/failed check
count and `not_tested`; the source comment carries the commit, the request and the run marker. Repeating
the delivery finds the same request and comment by marker, so nothing is created twice.

## What it does not do

No auto-merge, no deployment, no force-push, no second transport (email/Slack). Deployment and
confirmation are the next stage.
