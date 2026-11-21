## What changed

<!-- One paragraph. Link the task and the run. -->

## Evidence

- Task: `t-...`
- Run: `r-...`
- Proof page: `runs/<run>/evidence.md`
- Verdict: ALLOW / BLOCK
- Cost: tokens, USD, wall time

## Checks

- [ ] `make check` (ruff, mypy, coverage ≥ 80%) is green
- [ ] New tests fail before the change and pass after it
- [ ] No new TODO, no unexplained `# type: ignore`
- [ ] If a decision changed, an ADR is added or amended
- [ ] If `web/` changed, Playwright, axe and screenshot diffs are green

## Risk

<!-- What could break, and how it would be noticed. -->
