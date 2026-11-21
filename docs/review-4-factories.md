# Review 4 — two agent factories, one thesis

Sources read on 2026-11-21:

- OpenAI, “How OpenAI’s Performance Factory keeps ChatGPT fast”, 19 Nov 2026.
- @OpenAIDevs thread, 19 Nov 2026.
- Alex Greenshpun, “Attention Is the New Currency”, updated 14 Nov 2026.
- @alexgreensh, “Two agent factories, one idea: protect human attention”, 20 Nov 2026 and the
  attached comparison sheet.

These are self-reported accounts, not independent audits. The numbers are used as directional
evidence, not as targets.

## What the two systems agree on

| Mechanism | OpenAI | Alex | Works today |
|---|---|---|---|
| Persistent task with state and findings | task service + configurable workflow | task graph, brief, report, evidence | task events/projection/evidence; findings now added |
| Dispatcher | dispatch loop, cloud Codex turn | orchestrator + scheduler | `works dispatch` one pass or `--watch` |
| Waiting / wake | subscriptions on PR, CI, deploy | supervisor checks every lane | `waiting_review/ci/deploy` + `works wait/wake`; real webhooks pending |
| Independent challenge | adversarial session tries to disprove diagnosis and fix | reviewers on other model families; 6/10 send back | verifier planned in M2; challenge planned |
| Human attention | reviewed summaries, grouped incidents, impact rank | held decisions with default/deadline; 67 sessions/day without a message | proof page and two gates; grouping/ranking planned |
| Memory | task record, not raw profiling data | Total Recall, proactive recall 2,500+ times/month | PPMA reporting; recall planned |
| Evals | answer-stripped incident backtests, separate summary grader | golden fixtures from real failures, blind leak checks | mutation + scenario tests; agent evals planned |
| Self-repair | daily scan of tool/permission failures | cause-aware retries, nightly enforced rules | doctor only; loop planned |
| Merge / recovery | engineer merges; agent verifies metric | merge gate re-runs checks, live download checks | release/confirm planned in M3 |

## Numbers that shaped the plan

- OpenAI: 1,700+ investigations, 600+ root causes, 400 proposed fixes, **15 exact agent-authored
  PRs** shipped, ~50 informed a human fix; 70% of 100 reviewed diagnoses accurate; adversarial
  review sends back ~25%.
- Alex: **6 → 160** commits per 100 typed messages; **~5 → 17.6** agent-hours per human-hour;
  ~90% of sessions agent-started; **67** sessions/day with no human message; fixes **49.6% → 11.6%**
  of commits; bug reports/download **−2/3**; red CI **32% → 8%**; 12-day build = 141 sessions,
  461 review runs, 152 approved pieces.

The honest reading: autonomy scales diagnosis and small fixes; **review and merge stay scarce**.
That validates our two gates and proof page, and argues against measuring agent count.

## Adopted

1. Waiting states + wake subscriptions + dispatcher (T3.9, T3.10).
2. Structured findings and “what remains uncertain” on the proof (T1.15, T2.9).
3. Versioned prompts with hashes (T1.14).
4. Adversarial challenge on a separate session/provider (T2.10).
5. Agent eval suite with answer-stripped backtests and leak checks (T2.11).
6. Summary grader for an unfamiliar engineer (T2.12).
7. Attention metrics and dashboard from events only (T1.16, T4.10).
8. Clean-OS matrix, merge-result re-check, post-release metric confirmation (T3.11–T3.13).
9. Incident linking and impact ranking (T3.14).
10. PPMA recall before interrupting a person; self-repair loop (T4.8, T4.9).

## Rejected

- **Agent org charts and role personas.** Both sources argue the work decides the shape.
- **A zoo of models and tools before M3.** Real at Alex's scale, premature here.
- **Autonomous merge in v0.** The evidence says review is the bottleneck, not the missing button.
- **Vanity metrics** such as number of agents or sessions. We measure human attention and outcomes.

## Effect on the plan

Plan v4.5 added the parity tasks; v4.6 added Mira; v4.7 delivered the first P0 batch: prompt
registry, structured findings, attention metrics and the proof rubric. The GUI preview stays after
M1, the product window after M2.
