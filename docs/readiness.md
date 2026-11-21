# Readiness

`works readiness` answers one question before autonomy: **may this repository be automated at all?**
It is a gate, not a report. A red result means an autonomous run must not start.

## Configure

Add `.works/readiness.yaml` to the product repository:

```yaml
schema_version: 1
features: features
commands:
  lint: "{python} -m ruff check ."
  format: "{python} -m ruff format --check ."
  types: "{python} -m mypy src"
  tests: "{python} -m pytest -q -m 'not slow'"
  verify: "{python} -m pytest -q tests/smoke"
  architecture: "{python} scripts/check_boundaries.py"
suppressions:
  allow:
    - "src/legacy.py:10:noqa"
    - "tests/fixture.py:3:type-ignore"
```

- `{python}` is replaced by the running interpreter; commands are split into argv, never passed to a
  shell.
- `features` is a file or directory; at least one `.yaml`/`.yml` must exist.
- `suppressions.allow` is an exact allowlist of `path:line:kind` for `noqa`, `type-ignore`, `skip`
  and `xfail`. An unlisted suppression fails the gate.
- Missing commands fail when the gate runs; `--no-run` shows them as skipped for a fast preview.

## Run

```powershell
works readiness --repo C:\path\to\product
works readiness --repo . --json
works readiness --repo . --no-run     # static checks only
```

Exit code `0` is green, `8` (`EXIT_BLOCKED`) is red. `--json` returns every check, the suppression
list, unknown suppressions and the feature files.

`works run --live` also checks readiness before an autonomous run; a red gate appends
`readiness.checked` and refuses with `policy_error` before the builder starts. Without
`.works/readiness.yaml` every command check is red, so a live run is refused until the repository
opts in. Recorded (`--trace`) runs are not gated.

## What is checked

| Check | Meaning |
|---|---|
| Git repository | `.git` exists; the change can be bound to a commit |
| Project manifest | `pyproject.toml`, `package.json`, `Cargo.toml` or `go.mod` |
| Feature map | versioned feature files exist |
| Known suppressions | every suppression has an explicit allowlist entry |
| Lint, format, types | the repository's own commands |
| Fast tests | the cheap test path |
| Product verify | the product's own smoke/verify command |
| Architecture boundaries | the repository's structural check |

The GUI Evidence panel shows the static result; commands are not run from a GET request. In
`works ui --write` it also offers **Run checks**, which runs the full gate through a local-only
`POST /api/readiness` and replaces the panel with the result.

## Open

Import-boundary/dependency-graph checks and structural tests inside the independent verifier are
still M2. The feature-map **content** check is T2.19; readiness only proves that a map exists today.
