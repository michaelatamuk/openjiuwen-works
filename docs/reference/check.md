# Check (stage 6)

The plan names the checks; this stage runs them and decides whether the change is provable.

## Integrity of the check set

A plan records `scenario_sha`, a hash over every scenario id, script name and script content. At check
time the hash is recomputed: if a script changed after approval, the run stops with
`policy_violation` instead of testing a different definition of done. Test edits are already blocked by
the path policy.

## Base vs candidate (`WORKS_DIFFERENTIAL=1`)

Off by default because it doubles the check time. When on, Works runs the test node on a clean worktree
at the approved base commit and records `baseline_exit` and `baseline_output_sha256`. A candidate
failure whose exit code and last output line match the baseline is reported as **"the check already
failed at the base commit"**; it still blocks, because a proof cannot rest on a failing must-pass check,
but the reason is honest instead of blaming the change.

## Independent review

A reviewer with a different provider or a different credential is optional by default. With
`WORKS_REQUIRE_SPLIT_REVIEW=1`, high-risk work (risk level high/critical) is refused when the reviewer
shares the builder's provider and credential: the run stops with `challenge_failed` and the reason
"self-review". Low-risk work may share them.

## Flakes and repeats

Active flakes stop the verdict (`flaky_test`). `WORKS_REPEAT_SCENARIOS=2|3` runs each scenario two
or three times; if the outcome differs between runs, the run stops as `flaky_test` with the unstable ids
and is neither an allow nor a plain block. Missing dependencies or commands are `config_error`.
Scenario failures are `tests_failed` or `verdict_failed`, and evidence carries a typed **Next step**.

## Skipped checks

A flow node with `mode: off` is recorded in `skipped_checks`, so a proof names what it did not run
instead of hiding it.

## Evidence

Each command keeps argv, cwd, exit code, duration and output hash. The verdict lists P0/P1 outcomes;
`not_tested` carries residual risk. The proof binds all of it with the fingerprint.
