# M23 — decision support at the gate (design)

Status: planned. Wave one of `docs/design/feature-recommendations.md`: three low-effort features that
make the existing release gate usable by the person who has to sign it.

## Why

The release gate is the product's control point, and today it asks a person to read a diff, a test log
and a hash. Three things are missing:

- the approver has no classified risk, only their own reading of the diff;
- the reporter who says "still broken" has no path back into the system, so the next attempt starts
  blind;
- the evidence is written for engineers, while the gate is often a manager, a security reviewer or a
  compliance officer.

M23 does not add a stage and does not change who decides. It makes the decision informed, readable and
reopenable.

## What already exists

| piece | where |
|---|---|
| Risk level, reasons, owners, required reviewers | `domain/risk.py` (`rate_risk`) |
| Risk recorded in the evidence record | `Evidence.risk` |
| Proof binding over the whole record and the diff | `Evidence.bind()`, `proof_sha256` |
| Markdown proof page | `domain/evidence/render.py` |
| Delivery link to PR/issue and tracker comments | `application/delivery/` |
| Intake webhooks and source policy | `application/webhooks.py`, `interfaces/api/routes/hooks.py` |
| Evidence and release screens | `web/src/features/evidence`, `web/src/features/release` |

Nothing in M23 needs a new store, a new service or a new model call.

## Risk tier at the gate

`rate_risk` already answers "how risky is this change" from paths, diff size, the flow's high-risk
paths, coverage and recent incidents. M23 extends it with two cheap, deterministic signals:

- **complexity delta** — added and removed lines per file, and the number of functions or branches the
  diff touches when the language is known; reported as a number, not a score;
- **security surface** — paths matching the flow's sensitive areas (auth, crypto, payments, secrets),
  and changed-line coverage when the repository reports it.

Output stays `RiskRating`: a level, one-line reasons and the reviewers it implies. It is shown first on
the evidence page and in the release-gate payload, so an approver sees "high — auth path, 14 files"
before the diff.

Rules:

- the tier is computed **before** `bind()`, so it is covered by `proof_sha256` and cannot change after
  approval;
- a tier never opens, closes or blocks a gate; it is evidence, not policy;
- if a signal is unavailable, the reason says so instead of guessing.

## Plain-language summary

A second rendering for the same record, generated from fields the run already produced:

1. **What was wrong** — the task title and how it was reproduced.
2. **What caused it** — the root cause from the plan and the verifier findings, quoted, not inferred.
3. **What changed** — the files and the plan steps, in prose, no diff.
4. **What proves it** — the checks, the verdict, P0/P1 results and the binding hashes.
5. **What was not tested** — `not_tested`, verbatim.

The renderer is a deterministic template: no model call, no cost, no new claims. Wording rules are
part of the contract — no adjectives, no "likely", no numbers that are not in the record. When a field
is empty the summary says "not recorded" rather than inventing a sentence.

Binding and storage:

- the summary is generated before `bind()` and stored as `summary` plus an artifact of kind `summary`
  with its own SHA-256, so `proof_sha256` covers it;
- `proof.md` is unchanged and remains the technical page;
- evidence from before M23 has no stored summary: it is rendered on demand and marked `derived` in the
  API, and it is never written back into an old proof.

Surfaces: `GET` evidence returns `summary {text, sha256, derived}`; the UI toggles **Summary /
Technical** and opens on Summary at the release gate; `works proof <run> --summary` prints it.

## Reporter feedback loop

A comment on the original issue or ticket can reopen the task instead of starting from zero.

- **Event** — `reporter_replied` on the existing intake: source, task reference, comment id, author,
  body, url and timestamp.
- **Matching** — through the delivery link recorded when the change was delivered. If no link exists,
  the event is refused with a reason; M23 never guesses which task a comment belongs to.
- **Context** — the re-queued task carries the previous plan id and hash, a link to the previous proof
  and the reporter's text, so the planner sees what was tried and what still fails.
- **Guards** — idempotent by event id and comment id; bots and the system's own comments are ignored;
  only allowlisted sources are accepted; the scheduler still decides budget, labels and whether the
  task may start; at most three reopenings per task per day, after which the event is recorded and
  surfaced for a person.
- **Closed change** — if the PR or ticket is already closed, the reply is attached as context only and
  the task is not reopened automatically.

`works task retry <id> --note "..."` is the CLI path for the same context.

## Data changes

- `Evidence` gains an additive `summary` field and optional risk detail fields; defaults keep old
  records valid, so `schema_version` stays 1.
- One new event type and one new ledger reason (`reporter_replied`).
- No new database, no new configuration file, no change to `dispatch.yaml` beyond the existing source
  allowlist.

## Invariants

1. The plan and release gates keep exactly the same authority; M23 adds no blocking.
2. No new model calls: risk and summary are deterministic.
3. Evidence is immutable once bound; old proofs are never rewritten.
4. Intake policy remains in `dispatch.yaml`; the webhook handler does not decide labels or budget.
5. A missing signal produces a stated "not recorded", never a fabricated reason.

## Non-goals

A model-written summary, risk-based blocking, a chat with the reporter, writing back to the tracker
beyond the existing comment, reopening a merged PR automatically, multi-repo tasks, and any
per-person productivity metric.

## Acceptance

- risk tier is deterministic for the same input and covered by `proof_sha256`;
- the tier cannot open or close either gate (a test asserts the refusal path is unchanged);
- the summary contains all five sections, invents no numbers, and its hash equals the stored artifact;
- old evidence returns `derived: true` and keeps its original `proof_sha256`;
- the same webhook delivered twice re-queues once;
- an unknown reporter, a closed PR and a non-allowlisted source are each refused with a reason;
- the Summary/Technical toggle is covered by an e2e test and the CLI prints the summary;
- `mypy`, the web suite and the docs link check stay green.

## Work breakdown

| item | days |
|---|---|
| 23.1 risk extension and placement | 3 |
| 23.2 summary template, binding, API and CLI | 3 |
| 23.3 reporter event, matching and guards | 4 |
| 23.4 GUI parity and e2e | 1.5 |
| 23.5 docs, ADR and acceptance tests | 1.5 |
| **total** | **13 (~12 with reuse, ~14 with contingency)** |
