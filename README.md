# openJiuwen Works — story kit

Deck, concept film and working notes for **openJiuwen Works**: a software factory where one
signal goes in and a released fix comes out — and the fix goes back to where the bug was seen.

---

## What is in here

| Path | What it is |
|---|---|
| `deck/01-problem` | The problem, told as one week: 4 days the usual way, 1 h 45 min with Works |
| `deck/02-onepager` | How the loop works: 10 steps, 2 gates, the products it uses |
| `deck/03-why-now` | Why the timing works: what changed, what holds it up, flows, metrics |
| `deck/04-flow-file` | An appendix: what one flow looks like as a file |
| `deck/05-flow-boxes` | The same loop as ten boxes with the product used at each step |
| `video/` | The concept film, 47 s, two halves, one clock |
| `docs/demo-video-proposal.md` | The 1:55 storyboard and craft rules |
| `tools/` | Scripts that generate every frame, the audio bed and the MP4 |
| `anim/frames/` | Source frames of the film (SVG + PNG) |
| `archive/` | Earlier design passes, kept for reference |

Every slide ships as SVG (editable) and PNG (send-ready).

---

## The story in one line

> Writing code is fast. Waiting is slow. openJiuwen Works moves the waiting into an engine,
> keeps people at two gates, and puts the fix back where the bug was seen.

---

## Deck order

1. **The problem** — a customer in Berlin, an invoice with the wrong VAT, four days of waiting.
2. **How it works** — three ways in, one engine, ten steps, two gates.
3. **Why now** — the bottleneck moved; what a factory needs; flows and success metrics.
4. **Appendices** — the flow as a file, and as ten boxes.

---

## Reproducing the film

Requires Chrome, Python 3.11+ and ffmpeg.

```bash
python tools/make_anim.py      # renders the frames into anim/frames
python tools/make_audio.py     # synthesises ticks, dings and the pad
python tools/build_anim.py     # assembles video/openjiuwen-works-two-mondays.mp4
```

The narration lines are generated with Windows SAPI (`tools/anim_tts.ps1`); replace them with a
real voice-over and the edit stays the same.

---

## Status

A proposal, not a shipped product. Screens in the film are concept frames, not recordings of a
running system. Numbers are illustrative and labelled as such on the slides.
