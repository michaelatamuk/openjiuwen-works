# Competitor Analysis

*November 2026*

---

## Market Context

The autonomous bug-fix and software delivery space matured rapidly in 2026. The core reproduce →
plan → build → test → PR loop is now commodity — most serious players have it. The competitive
battleground has shifted to three axes:

- **Trust and auditability** — who can prove what was done and why
- **Enterprise/regulated market** — FedRAMP, local execution, data residency, compliance
- **Throughput** — parallel execution, proactive discovery without waiting for issue reports

The phrase "agentic software factory" entered mainstream usage in 2026 (Augment Code, Atlan, Qodo
all published definitions). Most describe an aspiration or a loose agent collection. No competitor
has shipped a full pipeline with named stages, human gates, and immutable evidence as a purchasable
product — except Works.

Key dynamic: the Nov 2026 paper *Do Coding Agents Catch Their Own Bugs?* confirmed agents cannot
reliably verify their own fixes. Every competitor that uses one agent for both build and verify is
architecturally compromised on this dimension. This validates Works' separate verifier design.

---

## Devin (Cognition) — Market Leader

**Status:** Market leader. $48B valuation (Sep 2026). Raised over $2B. Writes 89% of its own code.
75%+ of one major bank's technology teams use it.

**Key 2026 updates:**

- **Windows VM support** (May 2026) — runs and tests natively on Windows
- **FedRAMP High In-Process** (Jul 2026) — federal agency market unlocked
- **[Auto-Triage](https://cognition.com/blog/auto-triage)** (May 2026) — monitors Sentry, Pylon
  tickets; 6-stage pipeline: Triage → Launch → Investigate → Reproduce → Propose PR → Sync
- **[Devin Security Swarm](https://devin.ai/blog/devin-security-2)** (Jul 2026) — found 72% of real
  CVEs in a 50-CVE test at $90.23/run

**Pipeline depth:** ~3 real stages (investigate, fix, PR) structured as 6 labelled steps. No plan
gate. No separate verifier. No immutable evidence page. No formal verdict rule. Same agent that
builds also verifies.

**Key weakness:** cloud-only. Code leaves the customer's infrastructure. Cannot be used by
organisations with strict data residency requirements. The Nov 2026 paper
*[Do Coding Agents Catch Their Own Bugs?](https://arxiv.org/pdf/2611.01181)* confirms that agents
verifying their own fixes is unreliable.

**Competitive threat to Works:** highest. Moving toward regulated enterprise with FedRAMP. Has
proactive monitoring that Works lacks. $48B war chest. The main threat is Devin adding local
deployment and audit features over time.

---

## Claude Code and OpenAI Codex CLI — The Harness Layer

Neither is a pipeline competitor. Both are agent harnesses that Works orchestrates.

**[Claude Code](https://getunblocked.com/blog/claude-code-vs-codex/):** Anthropic's agentic CLI.
65.5% usage share among AI coding agents (Stack Overflow 2026 Developer Survey). 80.8% on SWE-bench
Verified — the highest of any measured agent. Runs in terminal, VS Code, JetBrains, desktop app
(macOS/Windows), iOS, Slack. Works uses it as the default builder.

**[OpenAI Codex CLI](https://getunblocked.com/blog/claude-code-vs-codex/):** Released April 2025.
29.5% usage share. OS-level sandboxing, strong on terminal/shell tasks. Enterprise security
controls. Works lists it as a supported harness provider.

**Relationship to Works:** both are execution engines. Works adds the pipeline, gates, evidence, and
verdict on top. The multi-provider harness design means Works is not dependent on either remaining
dominant — model capabilities shift every few months and the pluggable harness is the right hedge.

**Risk to watch:** if Anthropic or OpenAI build a full pipeline product on top of their own harness,
they would have distribution and trust advantages. No sign of this as of Nov 2026, but it is the
most plausible long-term competitive move.

---

## GitHub Copilot Workspace — Closest UX Analog

**Status:** Active product, ~$10/month, deeply GitHub-integrated.

**What it does:** Async cloud tool. Analyzes a GitHub issue, creates a plan, writes code, opens a
PR. Human reviews the plan before coding begins — the closest structural analog to Works' plan gate.

**Pipeline depth:** ~2 stages (plan, code). Has a planning step with human review. But: no
reproduction step, no separate verifier, no test verdict rule, no evidence page, no
deliver/deploy/confirm/escapes stages.

**Key weakness:** shallow pipeline. The plan review is a UI convenience — the human can edit the
plan but there is no formal gate with evidence, no blocked/reverted terminal state, no audit trail.
No auditability beyond the PR itself.

**Competitive threat to Works:** medium. Shares the human-in-the-loop positioning but is far less
rigorous. Loses on depth, auditability, and verifiability. Wins on price (~$10/month vs. the
operational cost of a full pipeline) and GitHub-native integration.

---

## Google Jules / Antigravity — Wound Down

**Status:** Jules being wound down December 31, 2026. Cutoff for new sessions: November 11, 2026.

**What Jules did:** Cloned repo into sandboxed Google Cloud, analyzed with Gemini 2.5 Pro, wrote
code, ran tests, opened PR. Fully async.

**Performance:** 51.8% on SWE-bench Verified vs Claude Code's 80.8% — a 29-point gap that likely
contributed to the wind-down decision.

**Replacement:** Google confirmed many Jules capabilities will continue under a unified product
called **Antigravity**. Details not yet public as of Nov 2026.

**Competitive threat to Works:** low currently (product in transition). Antigravity is the product
to watch. Google has the infrastructure, the model (Gemini), and the enterprise relationships to
compete seriously if Antigravity ships a full pipeline product.

---

## OpenHands — Open Source Self-Hosted

**Status:** Active, open-source, self-hostable. [All Hands AI](https://www.allhands.ai/).

**What it does:** Fully autonomous agent. Open an issue, it takes over. Self-host on your
infrastructure, plug in your own LLM. No code leaves your servers. Supports OpenAI-compatible base
URLs — any model works.

**Pipeline depth:** ~2 stages (investigate, fix/PR). No human gates, no evidence page, no verdict
rule. Single agent verifies its own work.

**Key strength:** self-hosted + open-source is a real differentiator for cost-sensitive or
OSS-preference buyers. No subscription. No data leaving infrastructure.

**Key weakness:** no audit trail, no structured pipeline, no formal verification. The same agent
that writes the fix decides if it passed. For regulated industries this is disqualifying.

**Competitive threat to Works:** medium for cost-sensitive or developer-first buyers. Zero threat in
regulated/enterprise market where auditability is required.

---

## DeepSeek dsh-superagent — New November 2026

**Status:** Released October 31, 2026. MIT-licensed research prototype from DeepSeek Harness team.
Not an official DeepSeek product.

**What it does:** Router + Worker architecture. One persistent router agent reads GitHub issues and
group chat messages (Feishu/Slack), dispatches to isolated parallel worker sessions each in their
own git worktree. Workers open PRs. Median task completion: 12.4 minutes, 95th percentile: 15.7
minutes.

**What it is NOT:** not a pipeline, not a factory. No stages, no reproduction step, no plan, no
verification, no evidence page, no human gates. It is a dispatcher that parallelises coding work.

**Relationship to Works:** not a competitor at the same layer. dsh-superagent could be used as the
worker harness inside Works — the DeepSeek harness integration (`dsh`) in the Works codebase already
anticipates this. The worktree isolation pattern is worth adopting for Works' parallel task
execution feature.

**Competitive threat to Works:** low directly. Indirectly signals DeepSeek is moving up the stack.

---

## OpenAI Internal Codex Factory — Not a Product

**Status:** Internal tooling. Reported by
[Gergely Orosz (Pragmatic Engineer)](https://newsletter.pragmaticengineer.com/p/openai-software-factory),
September 2026.

**What it does:**

- Intent and context: human defines outcome; Codex pulls from Git, GitHub, Slack, Notion, internal
  logs, custom skills
- Implementation: code changes, tests
- Parallel specialist review agents (data, infra, cloud, security) running simultaneously
- Risk classification before merge
- Supervised rollout
- Perf Factory: production signal monitoring, latency regression detection, auto-creates fix tasks
- Sevbot: incident response — gathers context, suggests mitigations in incident channel

**Assessment:** arguably the most sophisticated pipeline described publicly in 2026. Parallel
specialist reviewers, production feedback loop, incident integration — more advanced than Works in
those dimensions. Engineers increasingly function as product managers, defining outcomes while agents
handle implementation.

**Why it matters to Works:** it validates Works' architectural bets. Gates, specialist verifiers, and
production feedback loops all appear here, built by a team with unlimited resources. OpenAI is not
selling this — it is a proof of concept that the full pipeline approach works at scale. The features
it has that Works lacks (specialist verifiers, production loop) are the highest-priority additions.

---

## Research Landscape — Key 2026 Papers

**[Do Coding Agents Catch Their Own Bugs?](https://arxiv.org/pdf/2611.01181)** (Nov 2026)
Agents cannot reliably verify their own fixes. Directly validates Works' decision to use a separate
verifier with credential isolation.

**[Validation Evidence in LLM Repair Agents](https://arxiv.org/pdf/2607.28871)** (Jul 2026)
Many "passing" test results in agent repair pipelines don't actually test the original bug. Directly
validates Works' P0/P1 verdict rule and evidence page.

**[Active-SWE: Benchmarking Coding Agents for Proactive Bug Fixing without Issue Reports](https://arxiv.org/pdf/2608.04682)** (Aug 2026)
1,663 tasks, 6 bug categories, 8 languages. Most state-of-the-art agents struggle with proactive
bug-finding. Confirms reproduction without an issue report remains unsolved.

**[PROBE: Frontier Coding Agents Find Different Bugs Than Maintainers Fix](https://arxiv.org/pdf/2610.35987)** (Oct 2026)
Agents and human maintainers fix systematically different classes of bugs. Implies agent pipelines
and human workflows are complementary — supports Works' human-gate model.

**[EviACT: An Evidence-to-Action Framework for Agentic Program Repair](https://arxiv.org/pdf/2605.27238)** (May 2026)
Academic framework independently arriving at the same architecture Works uses: evidence collection
before action, not after.

**[Agentic Software Issue Resolution with LLMs: A Survey](https://arxiv.org/pdf/2512.22256)** (Dec 2025)
Maps the full taxonomy of approaches. Confirms the pipeline pattern is well-understood academically
but not yet productized with auditability — the gap Works fills.

---

## Positioning Map

| Product | Pipeline stages | Human gates | Immutable evidence | Separate verifier | Local/self-hosted | As product |
|---------|:-:|:-:|:-:|:-:|:-:|:-:|
| **openJiuwen Works** | 10 | Yes (optional) | Yes — SHA-256 | Yes | Yes | Yes |
| Devin Auto-Triage | ~3 | No | No | No | No (cloud) | Yes |
| OpenAI internal factory | ~7 | Partial | No | Partial | N/A | No |
| GitHub Copilot Workspace | ~2 | Partial | No | No | No (cloud) | Yes |
| Google Jules | ~2 | No | No | No | No (cloud) | Winding down |
| OpenHands | ~2 | No | No | No | Yes | Yes (OSS) |
| DeepSeek dsh-superagent | 1 (dispatch) | No | No | No | Yes | Prototype |

---

## Where Works Is Uncontested

Three capabilities have no current competitor as of November 2026:

**1. Immutable evidence page with SHA-256 binding to the exact diff.** The research community in
2026 is writing about why audit trails must be evidence, not just logs — describing architectures
that match what Works has already built. No competitor has shipped this.

**2. Formal verdict rule (P0 must pass, P1 ≥ 80%).** Every other product has vague "tests pass"
heuristics or no rule at all. Works has an auditable, explainable rule that a manager or compliance
officer can read, understand, and cite in a review. This is the difference between a tool and a
control.

**3. Full pipeline as a purchasable product: reproduce → plan → build → verify → prove → release →
deliver → deploy → confirm → escapes.** The concept is widely discussed in 2026. Only Works ships
it end-to-end with named stages, optional human gates, and immutable evidence. OpenAI's internal
factory is more sophisticated but is not for sale.

The uncontested zone maps precisely to the regulated and enterprise buyer: organisations that cannot
send code to the cloud, need an audit trail that passes legal review, and must demonstrate to a
regulator or auditor that every change was proven before it shipped. The main timing risk is Devin
adding local deployment before Works establishes that customer base.
