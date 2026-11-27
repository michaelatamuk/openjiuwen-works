# Review 1 — self-critique of `docs/roadmap/plan.md` v1

Written before any code. Each point is a gap that would cost time or credibility later.

## Blocking gaps

1. **No reconnaissance.** The plan assumes we can run the target repo's tests, that they are fast and
   not flaky, and that one issue is small enough. None of that is verified. This is the single
   largest unknown and it has no task.
2. **No baseline.** We promise "under one working day" without measuring how long the same issue
   takes today. Without a baseline the metric is a slogan.
3. **Scenario leakage is hand-waved.** "Stored outside the worktree" is not enough: if scenarios live
   in the same repository, the builder reads them from git history or from the clone.
4. **The plan builds components before value.** M1 lists seven components; nothing runs end to end
   until the end of week 4. A thin end-to-end slice on a fixture repo should come first, with a fake
   harness.

## Design gaps

5. **Scenario authoring has no method.** "At least eight scenarios" says nothing about who writes
   them, how they are reviewed, or what makes one good. This is the actual product work.
6. **The verifier is only checked by mutation.** No agreement measurement between the LLM judge and a
   human on the same scenarios; no false-positive budget.
7. **No prompt registry.** Traces store a prompt hash, but there is no way to compare runs across
   prompt versions or to roll one back.
8. **No revert path.** T3.5 mentions a reverted PR but no task owns the revert and the post-mortem.
9. **"The factory improves itself" is a report, not a loop.** T4.3 counts numbers; nothing turns a
   repeated failure into a new scenario, test or rule.
10. **No sandbox decision.** Commands run on the host with network access. Worktree isolation is not
    security isolation.

## Planning gaps

11. **No estimates per task** and no owner model. Solo or team changes the order.
12. **No issue-selection criteria.** Which issues are in scope for v0: size, area, no migrations?
13. **No kill criteria.** When do we stop and say the approach does not work here?
14. **No forge assumption.** "PR" and "CI" are GitHub-flavoured but never stated; the target may be
    GitCode or an internal forge.
15. **Human minutes are a target, not an instrument.** Approvals carry no timestamps, so the metric
    cannot be computed.
16. **Escapes have no definition.** Found how, over what window, by whom.

## Verdict

v1 is a component plan, not a delivery plan. It needs reconnaissance, a thin slice, a scenario
method, leak prevention, a revert path and a learning loop before it is honest.
