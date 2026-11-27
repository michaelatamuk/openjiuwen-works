# Proactive scan

```bash
works scan --repo ../service --command "{python} -m pytest -q"
works scan --repo ../service --command "npm test" --dry-run --json
```

Runs a repository's own check once, compares the failures with the last scan of the same repository and
command, and files a task only for a **new** failure.

## Baseline

The last failure ids are stored in `~/.works/state/scan/<digest>.json`, keyed by the resolved repository
path and the command. Nothing is written into the repository.

- a new failure creates one task;
- a known failure creates nothing;
- a failure that no longer appears is removed from the baseline;
- a green run clears the list;
- `--dry-run` creates no task and leaves the baseline untouched.

## Failure ids

Pytest-style lines are parsed:

```text
FAILED tests/test_core.py::test_add - AssertionError
ERROR tests/test_setup.py::test_db - fixture
```

A non-zero exit with no such line becomes one stable id, `command-<hash>`, derived from the exit code
and the last lines of output. The same broken build does not create a new task on every scan.

## The task

A scan task is a normal `fix-issue` task:

- source kind `detector`, channel `scan`, ref `scan:<failure>`;
- severity `S3`, label `scan`;
- reproduction hint: run the command; the named check failed in the latest scan;
- dedupe key `scan:<repo+command>:<failure>`.

It goes through the queue, the scheduler, the budget and both human gates like any other task. The scan
never starts a run and never opens a gate.

## Not claimed

- No scheduled or daemon-side polling yet; the command is explicit.
- Only pytest-style failure lines are understood; other runners produce the stable command failure.
- No flaky-test suppression, sharding or automatic repair.
- The command runs with your OS permissions; use a repository and command you trust.
