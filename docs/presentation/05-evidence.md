# Evidence

What can be shown, not asserted. Numbers are from the current repository at the time of this draft
(2026-11-27); refresh them before the final deck.

## The product exists

- The loop runs end to end: intake, reproduce, plan, plan gate, build, check, proof, release gate,
  deliver, confirm.
- The daemon, the API, the SPA, the queue, the scheduler and the proof are in the repository.
- The deterministic demo runs without a model or network.

Source: `docs/start/status.md`, `README.md`.

## The proof is bound, not narrated

`works proof verify <run-id>` recomputes:

- the diff hash against `diff_sha256`;
- the proof fingerprint from the page itself;
- every artifact's SHA-256 against the file in the run directory;
- the event root against the recorded event range.

A tampered diff, a changed artifact, an edited page or a removed event fails with the failing check
named. `evidence.json` is the proof; `evidence.md` is a rendering.

Source: `docs/reference/lifecycle/proof.md`.

## Checks outlive the change

- Flows, checks, scenarios and risk rules are read from the base commit, not the worktree.
- The builder cannot edit the tests that judge it; test paths are denied by policy.
- A new commit invalidates the verdict and the approval; the gate re-checks at the merge commit.

Source: `docs/reference/lifecycle/check.md`, `docs/design/adrs/012-trusted-base-and-risk.md`,
`docs/design/adrs/004-isolation-boundaries.md`.

## The verifier is independent

- The verifier runs as a separate process or a Docker container with no network.
- It does not receive the builder transcript.
- The challenger can use a separate provider; the split is recorded.
- The local verifier is the default; a container run is opt-in and refuses to pretend when Docker is
  unavailable.

Source: `docs/reference/lifecycle/check.md`,
`docs/design/adrs/005-verifier-independence.md`.

## The two gates are real

- `actor_kind` must be `person`; agents are refused server-side.
- Identity is a name plus a device label.
- Quorum is optional and refuses the same pair twice.
- Approval has an expiry and is bound to the plan hash or the proof/commit.
- `gate.decided` is append-only.

Source: `docs/reference/lifecycle/gates.md`.

## Architecture, not a wrapper

- One local daemon owns a writable home (ADR 016).
- One bounded `ThreadPoolExecutor` for jobs (ADR 019).
- One scheduler loop that selects and claims, never runs or decides (ADR 024).
- The CLI and the daemon host the same supervisor; the queue, events and proof are shared.
- Events are the source of truth; projections and the SQLite index are derived.

Source: `docs/design/architecture.md`.

## Engineering evidence

At the time of this draft:

- `1000 passed, 5 skipped, 2 deselected` on the non-slow suite.
- 80.39% line coverage, above the 80% gate.
- Typing ratchet holds at 349 `Any` errors, no growth.
- 44 HTTP route classes classified; 0 API breaking changes.
- 8 versioned prompts with matching hashes.
- 27 ADRs; 55 registered documentation pages.

These are hygiene, not the pitch. Use one line if asked "is it real?"; do not turn the deck into a CI
report.

## Built vs proposed

| Piece | State |
|---|---|
| Queue, daemon, API, SPA | built |
| Scheduler, leases, estimates | built |
| Plan gate, release gate, proof, verifier | built |
| openJiuwen harness adapters (Claude Code, DSH, native, Codex) | built |
| JiuwenSwarm adapter and doctor | built; live gateway config external |
| Works MCP tools: `submit_signal`, `list_tasks`, `task`, `evidence`, `release` | built |
| Orbit calling Works over MCP | proposed |
| Orbit as a Works build adapter | proposed |
| Works accepting a signal from an Orbit room | proposed |

Source: `docs/design/strategy/positioning.md`, `docs/guides/integrations/live-harness.md`,
`docs/guides/integrations/swarm.md`.

## What to show live

1. Queue with five example tasks, one waiting at the release gate.
2. One task's Story: reported → picked up → confirmed → fixed → checked → delivered.
3. The plan gate: plan, checks, approve/reject.
4. The proof: diff, commands, verdict, risk, not tested, cost, model/prompt hashes.
5. The release gate: approve, deliver, confirm.
6. `works proof verify <run-id>` on the proof.

If the live demo fails, use `docs/assets/ui/story.png` and the proof page screenshot.
Never debug the demo in front of the audience.
