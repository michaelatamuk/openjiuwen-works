# Prompts and golden evals

Two small controls keep model behaviour from drifting silently.

## Prompt registry

Every shipped prompt under `flows/*/prompts/*.md` is listed in `flows/prompts.lock.json` with its
SHA-256, a named owner and a changelog. A run records the hash it used as `prompt_sha256` in the
proof, so a page says exactly which prompt produced it.

```bash
make prompts                       # verify; exits 1 on a mismatch
python scripts/check_prompts.py --update   # after an intentional edit
```

`--update` preserves the existing owner and changelog, so an edit needs a new changelog entry in
review rather than being absorbed by the hash bump.

## Golden evals

`evals/` holds recorded cases with explicit denominators: 30 planner inputs, 20 question/answer
pairs with citations, 12 injection attempts. `scripts/run_evals.py` scores them, enforces per-suite
thresholds and fails when a suite drops more than 2 percentage points below `evals/baseline.json`.

```bash
make evals
```

The suites are deterministic and call no model, so they run on every push. See `evals/README.md`
for what they do and do not prove.
