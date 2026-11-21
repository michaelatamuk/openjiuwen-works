# ADR-015 — The task is a line; Mira is the courier

**Status:** accepted · 2026-11-21

## Context

The Summary/Evidence split answers different audiences, but it is still a set of cards. A factory's
natural shape is a line: signal in, work through stations, proof out, fix back to the source.
Competitors show stage columns (Warp), timelines (Devin), mission control (Factory) or side-by-side
artifacts (Copilot); none makes one task a cinematic, replayable line with a courier.

Mira is already the brand's courier: she carries the signal in and the proof back. Using her as a
static empty-state image wastes the metaphor.

## Decision

- Add a **Story** view as the default for a selected task.
- The Story line starts with a gray **Reported** origin — the signal, not part of Mira's journey —
  then five Mira stops: **Picked up → Confirmed → Fixed → Checked → Delivered**.
- Every stop has four states: **not started** (dimmed), **Mira is here** (violet, work in the
  middle), **done** (green) and **stopped** (red). The release gate adds **waits for you** (amber).
  The label follows the state: “Mira is fixing it”, “Fixed”, “Mira stopped while fixing”.
- A **Technical line** lives inside **Evidence**: ten stations with gates, retries, artifacts and
  exact event times.
- Mira is the **current-milestone marker**, not a chat avatar and not a decoration. She appears in
  the hero and at the current station, and the station copy reads as a sentence: “Mira confirmed
  it”, “Mira fixed it”, “Mira checked it”, “Mira is ready to release”. Future stations never show
  Mira.
- Gates are stations with a diamond, owner and decision time. Mira waits beside a gate; she never
  replaces the human decision.
- Every station and artifact is derived from `events.jsonl` and `evidence.json`; no fake progress.
- A replay scrubber plays the real event sequence, kept behind “How we got here”; `?at=` deep-links
  a moment.
- Present mode hides the chrome for demos; `C` toggles it, `Esc` leaves it.
- Evidence remains for engineers. The human Summary is folded into the Story hero and receipt
  strip, not a third tab.

## Consequences

- The default screen becomes more engaging and more useful to a reporter, while the engineer keeps
  the full evidence one click away.
- The line must be driven by a real pipeline payload; a decorative animation is a defect.
- Mira needs poses over time (waiting, plan, proof, delivery, blocked); the preview uses one marker
  until T1.18 poses land.
- Mobile uses a horizontally scrollable route; reduced motion keeps the truth without animation.
- The final React/Vite window can reuse the same `pipeline` payload and station components.

## Alternatives rejected

- **Cards only**: accurate but does not show sequence, gates or where the fix is now.
- **Kanban columns**: good for the queue, weak for one task's journey.
- **Pure timeline**: precise but not spatial; the factory metaphor is lost.
- **3D game**: expensive, inaccessible and not more truthful.
- **Animated progress without events**: theatre; forbidden by the proof principle.
