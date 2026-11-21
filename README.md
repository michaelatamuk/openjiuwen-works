# openJiuwen Works

A software factory: one signal goes in, a released fix comes out — and the fix goes back to
where the bug was seen.

**Status: proposal.** Nothing in `src/` is implemented yet. The repository currently holds the
problem statement, the design, the deck and a concept film.

---

## The idea

Today a bug spends days in queues: for triage, for an agent's answers, for a reviewer's time,
for someone to prove the change works. Writing the code is the short part.

openJiuwen Works moves the waiting into an engine. It takes a signal from three places — a
failure caught by DigitalMate, a bug already filed in a tracker, a person reporting it — and
carries it through ten steps. People appear at exactly two gates: the plan and the release.

What comes back is not a diff to read. It is one page: what changed, what was tested, what it
cost. Then the fix ships to the app, the tracker or the person who reported it, and the report
closes.

---

## What is in the repository today

| Path | What it is |
|---|---|
| `docs/plan.md` | The development plan: preconditions, 5 milestones, ~70 checkbox tasks |
| `docs/review-1-self.md` | Self-critique of plan v1 |
| `docs/review-2-industry.md` | What Stripe, Ramp, Warp and StrongDM do that the plan first missed |
| `docs/review-3-external.md` | Independent review of plan v2 |
| `docs/deck/` | Five slides: problem, how it works, why now, flow file, flow boxes (SVG + PNG) |
| `docs/video/` | Concept film, 47 s: one clock, one timeline, two people |
| `docs/video-proposal.md` | The 1:55 storyboard and craft rules for a live-action cut |
| `docs/frames/` | Source frames of the film |
| `scripts/` | Generators for every frame, the audio bed and the MP4 |
| `src/` | The product. Empty on purpose. |
| `archive/` | Earlier design passes, kept for reference |

---

## Deck order

1. **The problem** — a customer in Berlin, the wrong VAT, four days of waiting.
2. **How it works** — ten steps, two gates, the products it uses.
3. **Why now** — the bottleneck moved; what a factory needs; flows and success metrics.
4. **Appendices** — the flow as a file, and as ten boxes.

---

## Design in one paragraph

A **window** and an **engine**. The window is where a person reports, watches and approves. The
engine owns the queue, the check and the proof. Everything else is a tool it calls: `jiuwenswarm`
builds in a worktree and runs CI, `agent-core` runs the checking agent in a clean context, `PPMA`
keeps the project state, `Orbit` optionally shares the proof with a team room. Nothing is forked;
every link is a published contract.

---

## Building the deck and the film

Requires Chrome, Python 3.11+ and ffmpeg.

```bash
python scripts/make_anim.py     # frames -> docs/frames
python scripts/make_audio.py    # ticks, dings and the pad
python scripts/build_anim.py    # docs/video/openjiuwen-works-two-mondays.mp4
```

Narration is generated with Windows SAPI (`scripts/anim_tts.ps1`). Swap in a real voice-over
and the edit stays the same.

---

## Numbers

Two only: **4 days** the usual way, **1 h 45 min** with Works. Both are illustrative and labelled
as such on the slides.
