# Feature Recommendations

*November 2026 — derived from competitive analysis and independent pipeline assessment*

---

## Overview

Ten features derived from competitive analysis (Nov 2026) and independent assessment of the Works
pipeline. Sources: codebase review, web research on Devin, Claude Code, OpenHands, DeepSeek
dsh-superagent, OpenAI internal factory, and six key 2026 research papers.

Three lenses used to evaluate each feature:

- **Impact** — does it strengthen Works' core promise (provable fixes, human oversight, auditability)?
- **Effort** — how much does it require new pipeline stages vs. extending what exists?
- **Competitive pressure** — are rivals moving here fast?

---

## Feature 1: Proactive Bug Discovery (Scan Mode)

**Competitive source:** Devin Auto-Triage (May 2026) monitors Sentry errors proactively. DeepSeek
dsh-superagent watches developer group chats without being tagged. The
[Active-SWE benchmark](https://arxiv.org/pdf/2608.04682) (Aug 2026) measures agents finding bugs
*without* issue reports — and shows all current agents struggle at it.

**Gap in Works:** entirely reactive. The pipeline starts only when a bug report arrives via intake
(GitHub Issue, Jira, detector alert). There is no path that finds bugs first.

**What it looks like:** a new intake source type (`scan`) that runs on a schedule. It executes the
existing test suite, static analysis, and security checks against the target repo. Any new failure —
a test that wasn't failing before, a new lint error, a new CVE in the lockfile — becomes a task
automatically, feeding the existing reproduce → plan → build pipeline unchanged.

**Effort:** low-medium. No pipeline changes. New intake adapter only.

**Risk:** false positive rate. Scan-generated tasks may be noisy. Mitigate with a confidence
threshold and a triage step before full pipeline execution.

---

## Feature 2: Parallel Task Execution

**Competitive source:** dsh-superagent's (Oct 2026) one genuine architectural insight is isolated
git worktrees per task, running in parallel. OpenHands does this too. Devin runs thousands of
sessions simultaneously.

**Gap in Works:** the queue processes tasks sequentially per repo. If a codebase has five open bugs,
they line up behind each other.

**What it looks like:** per-task git worktrees and concurrent supervisor loops for independent tasks.
The append-only queue and state machine already record independent task records cleanly — the missing
piece is worktree isolation so parallel runs do not corrupt each other's working tree, and a
concurrent supervisor that can drive multiple tasks simultaneously.

**Effort:** medium. Queue and state machine need no changes. Worktree lifecycle management and
concurrent supervisor scheduling are new.

**Why it matters:** the pipeline's value compounds with throughput. A team with 20 open bugs gets
dramatically more leverage from parallel execution than sequential. This also reduces mean time to
fix, which is the metric engineering managers track.

---

## Feature 3: Risk Scoring at the Release Gate

**Competitive source:** OpenAI's internal Codex factory (reported Sep 2026) runs automated risk
classification before code is merged — blast radius, security surface, complexity delta — as parallel
specialist passes.

**Gap in Works:** the release gate presents the human with an evidence page, but no synthesised risk
signal. The human must read the diff and form their own judgment with no structured summary.

**What it looks like:** a lightweight analysis pass that runs before the release gate opens. It scores
the diff on: lines changed, files touched, cyclomatic complexity delta, security-sensitive paths
modified (auth, crypto, payments), test coverage of changed lines. Output: a risk tier (low / medium
/ high) with one-line reasons, embedded as a new section at the top of the evidence page.

**Effort:** low. New analysis pass before gate, no pipeline restructure. The evidence page already
accepts new sections.

**Why it matters:** the human at the release gate is the last check before code ships. A synthesised
risk score helps them spend attention on what matters. It also creates an auditable record of risk
classification — valuable in regulated industries where reviewers must demonstrate they considered
risk.

---

## Feature 4: Separate Specialist Verifiers

**Competitive source:** OpenAI's internal pipeline runs parallel specialist agents — security,
infrastructure, data — not one generic verifier. The Nov 2026 paper
*[Do Coding Agents Catch Their Own Bugs?](https://arxiv.org/pdf/2611.01181)* confirms agents cannot
reliably verify their own fixes. The Jul 2026 paper
*[Validation Evidence in LLM Repair Agents](https://arxiv.org/pdf/2607.28871)* shows many passing
tests do not actually test the original bug.

**Gap in Works:** one verifier with one model and one credential set. It checks correctness but not
security, not performance, not data integrity.

**What it looks like:** the verify stage spawns specialist sub-verifiers based on which code paths
the diff touches. A diff modifying auth routes spawns a security-focused verifier. A diff on a hot
path spawns a performance verifier. Each runs independently with its own system prompt, its own
credential (the credential-split pattern already exists in Works), and reports findings back to the
evidence page under separate headings.

**Effort:** medium. New verifier personas and parallel execution in the verify stage. The harness
interface and credential split are already in place.

**Why it matters:** adversarial specialised reviewers catch different failure modes than a single
generalist. This is the most direct architectural response to the research showing single-agent
verification fails.

---

## Feature 5: Production Feedback Loop

**Competitive source:** OpenAI's internal Perf Factory monitors production after deploy, detects
latency/error regressions, and auto-creates fix tasks. This is the only system that closes the full
loop from bug report through to production health confirmation.

**Gap in Works:** the escapes step detects post-deploy problems but is reactive — a human notices and
files a new issue, losing prior context. There is no path from production telemetry → new task with
the previous evidence pre-attached.

**What it looks like:** Works already ships OpenTelemetry. A lightweight integration records baseline
error rate and latency at the deploy confirmation step. After confirmation, it monitors for
divergence. If production drifts from baseline beyond a threshold, it auto-creates a new task with:
the production signal, the original task ID as context, and the previous evidence page linked so the
planner sees what was tried.

**Effort:** medium. OTel integration, baseline recording at confirm step, drift detection, new task
creation trigger, PPMA extension to store baselines.

**Why it matters:** currently Works produces a proven fix but cannot know if that fix held in
production. Closing this loop turns the product from a "fix delivery tool" into a "production
reliability system" — a significantly more valuable positioning.

---

## Feature 6: Reporter Feedback Loop

**Gap identified independently** from reading the Works design: the product promises to return the
proven fix to the original reporter, but the intake is one-way. GitHub Issue in, PR out. If the
reporter says "this doesn't fix it," that signal goes nowhere structured — they file a new issue,
the prior context (plan, what was tried, what the evidence showed) is lost.

**What it looks like:** a reply on the original GitHub Issue or Jira ticket triggers a re-run. The
reporter's feedback is attached to PPMA as context for the planner: previous plan, what was tried,
what the reporter says still fails. The existing intake adapters (GitHub, Jira) already have webhook
support — this is a new event type (`reporter_replied`) on those webhooks feeding a task re-queue.

**Effort:** low. New webhook event type on existing intake adapters. PPMA context attachment. No
pipeline changes.

**Why it matters:** this closes the loop the product already promises. Without it, the reporter's
feedback is invisible to the system. With it, failed fixes become smarter on retry — the planner
sees its own prior attempt and the reporter's objection side by side.

---

## Feature 7: Plain-Language Evidence for Non-Engineers

**Gap identified independently:** the evidence page is engineer-facing — diffs, test results,
SHA-256 hashes, command logs. In the enterprise and regulated market Works targets, the approver at
the release gate is sometimes a manager, compliance officer, or security reviewer who cannot read
a diff.

**What it looks like:** a secondary rendering of the evidence page generated by a separate summariser
pass after the prove step. Contents: what the bug was, root cause found, what was changed and why,
what tests confirmed it — in plain prose, no code. Same SHA-256 binding as the technical page,
different audience. The UI shows a toggle between Technical View and Summary View.

**Effort:** low. New rendering pass in the prove step. UI toggle. No pipeline changes. The summariser
does not need to be the same model as the builder or verifier.

**Why it matters:** regulated enterprises have sign-off processes where non-engineers must approve
changes before release. Without a readable summary, Works forces those approvers to either trust
engineers blindly or skip the gate entirely. A plain-language rendering turns the evidence page into
a document any approver can act on — which is what makes the release gate function as a real
control, not a rubber stamp.

---

## Feature 8: SWE-Bench Evaluation Mode

**Competitive source:** every serious competitor publishes a SWE-bench Verified score. Claude Code:
80.8%. Jules/Gemini: 51.8% (and was wound down). Without a published number, Works cannot be
compared by buyers who now expect to see scores before making purchasing decisions.

**What it looks like:** an eval mode that runs Works against
[SWE-bench Verified](https://arxiv.org/pdf/2512.22256) or the new
[Active-SWE dataset](https://arxiv.org/pdf/2608.04682) (1,663 tasks, Aug 2026). Reports: fix rate,
false-positive rate (patches that pass tests but don't fix the bug), evidence quality score. The
deterministic planning fallback already in Works means the structural pipeline can be exercised
without live model costs — useful for CI-level pipeline regression testing.

**Effort:** medium. Dataset integration, eval runner, scoring logic, report generation.

**Why it matters:** primarily a marketing and credibility tool, but also a self-improvement
instrument. Running against a benchmark continuously identifies which bug classes the pipeline
handles poorly, feeding prioritisation of improvements. Without it, Works is arguing from
architecture diagrams against competitors arguing from numbers.

---

## Feature 9: Dependency CVE Pipeline

**Competitive source:** [Devin Security Swarm](https://devin.ai/blog/devin-security-2) (Jul 2026)
found 72% of real CVEs in a 50-CVE test at $90.23/run. Works already ships `pip-audit` and
`osv-scanner` for its own dependencies.

**Gap:** Works does not ingest CVE feeds (OSV, NVD, GitHub Advisory Database) as intake sources for
target repos. A CVE is a structured bug report with reproduction already defined — the exploit or
PoC — which sidesteps the reproduction problem entirely.

**What it looks like:** a new intake adapter polling CVE feeds for dependencies in the target repo's
lockfile. Each matched CVE becomes a task. The reproduce step writes a test that exercises the
vulnerable code path using the CVE's PoC. The build step upgrades the dependency or applies the
patch. The evidence page includes CVE identifier, CVSS severity, and the test proving the fix. This
is exactly the regulated-industry use case Works is positioned for — an auditable,
cryptographically-bound record of every security fix.

**Effort:** medium. New intake adapter, CVE-to-task mapping logic, evidence page extension for
security metadata.

**Why it matters:** high-value for financial services, healthcare, and defence contractors. These
buyers already run pip-audit and osv-scanner manually. Works can automate the full fix-and-prove
cycle for them, with an evidence page that satisfies auditors.

---

## Feature 10: Multi-Repo Coordination

**Gap identified independently:** in microservice architectures, a bug fix often requires a change
to a service *and* its client library, or to a shared schema *and* all consumers. Works is designed
around single-repo tasks. This is not a gap today — most bug fixes are single-repo — but it becomes
a ceiling as Works moves upmarket into large enterprise codebases.

**What it looks like:** a new task type that declares a dependency graph across repos:
`depends_on: [repo-a, repo-b]`. A coordinator sequences the per-repo pipelines: fix repo-a first,
run cross-repo integration tests, then fix repo-b. No single repo is released until all pass. The
evidence page spans all repos with a combined verdict. The append-only queue, state machine, and
gates are already well-suited to this — it is an extension of the existing pattern, not a redesign.

**Effort:** high. New task type, cross-repo coordinator, cross-repo integration test harness,
combined evidence page.

**Recommendation:** roadmap item, not near-term. Build the single-repo pipeline to maturity first.
Add multi-repo when a specific enterprise customer requires it and is willing to co-develop the
requirements.

---

## Priority Ranking

| # | Feature | Impact | Effort | Competitive pressure | Sequence |
|---|---------|--------|--------|----------------------|----------|
| 1 | Risk scoring at release gate | High | Low | Medium | First |
| 2 | Reporter feedback loop | High | Low | Low | First |
| 3 | Plain-language evidence | Medium | Low | Low | First |
| 4 | Parallel task execution | High | Medium | High | Second |
| 5 | Proactive scan mode | High | Medium | High | Second |
| 6 | Dependency CVE pipeline | High | Medium | High | Second |
| 7 | Specialist verifiers | High | Medium | Medium | Third |
| 8 | Production feedback loop | High | Medium | Medium | Third |
| 9 | SWE-bench eval mode | Medium | Medium | High | Third |
| 10 | Multi-repo coordination | High | High | Low | Roadmap |

**First (1–3):** low effort, strengthen the core promise immediately. Risk scoring and plain-language
evidence make the release gate more useful to non-engineers. Reporter feedback closes a loop the
product already promises.

**Second (4–6):** throughput, discovery, security — the three highest competitive pressure areas.
Devin is moving into all three. These defend the market position.

**Third (7–9):** deepen verification quality and establish benchmark credibility. Specialist
verifiers directly address the research finding that single-agent verification fails.

**Roadmap (10):** multi-repo when a specific enterprise customer requires it.
