# Mira — the mascot

**Mira is a magpie courier.** She carries the signal in and the proof back.

A magpie is the right animal for this product for three reasons:

1. **A messenger.** The loop starts with a signal and ends where the bug was seen; Mira is the one
   who makes the return trip.
2. **Collects what shines.** Evidence, commands, hashes and the one line that matters. She is a
   collector, not a generator.
3. **Not a machine.** A small, clever, slightly bossy bird makes the product feel like a place
   where people work, not a control panel for agents.

`mira` also means “look” in Spanish and Italian, and “peace/world” in Slavic languages. Her job is
to say: *look here — this is the proof, and this is what still needs you.*

## Personality

- Calm, curious, precise. She has seen a hundred runs and does not panic at a red one.
- Never chatty. She speaks in short, useful sentences: “Mira has the proof.”, “Mira needs your
  call.”
- She never celebrates before the verdict. The stamp comes after the scenarios pass.
- She is a colleague, not an assistant persona. No “Oops!”, no emoji storms, no fake enthusiasm.

## Where Mira appears

| Place | Pose | Rule |
|---|---|---|
| Empty queue | perched, tail flick | “No tasks yet. Mira is watching the queue.” |
| Waiting for a plan/release decision | holding a small card | “Mira needs your call.” The card names the decision and the default deadline. |
| Running | carrying a page, in motion | Progress is still shown as text and steps; Mira never replaces status. |
| Proved | stamping the proof page | After the verdict, not before. |
| Blocked | sitting beside the block reason | She looks attentive, not sad; the reason is the message. |
| Docs / README / deck | primary courier pose | Brand moment, not decoration on every page. |
| Favicon / avatar | head only | Must read at 16 px: eye, beak, violet scarf. |

Mira does **not** appear inside error text as a joke, does not block a control, and is not a chat
avatar. If a screen has Mira and no text, the screen is wrong.

## Voice

- “Mira is watching the queue.”
- “Mira has the proof.”
- “Mira needs your call: approve the plan, or it waits.”
- “Mira is carrying this back to the issue.”

Short, declarative, no exclamation marks. The same voice in CLI human output and GUI empty states.

## Visual rules

- Flat vector, rounded geometry, ink `#111827`, paper `#F4F5F9`, violet `#6D28D9`, lavender
  `#DDD6FE`, warm amber beak `#D97706`.
- Big head, small body, one visible eye ring, a long tail, a tiny proof page. No gradients on the
  character; the only shadow is a soft ground ellipse.
- A violet scarf is the constant. It is how you recognise her at 16 px and in monochrome.
- Motion: blink every ~6 s, tail flick, page flutter. All of it stops under
  `prefers-reduced-motion`; nothing moves in a loading state for more than 2 s.
- Alt text: “Mira, a magpie courier, carrying a proof page.” When the adjacent text carries the
  meaning, the image is `aria-hidden`.

## Assets

- `brand/mascot/mira-primary.svg` — full courier pose.
- `brand/mascot/mira-avatar.svg` — head, favicon and small avatar.
- Original character. No third-party likeness, no AI-generated artefact; the SVG is the source.
