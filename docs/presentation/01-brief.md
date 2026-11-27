# Brief

## Audience

Product and engineering leadership, partners and technical buyers. They know what an agent, a
harness and a coding tool are. They do not know why Works is a separate product.

They are not empty vessels: they have seen demos, they have tried Claude Code or Codex, and they have
heard "agent factory" before. The deck has to survive the question "why won't the vendor just add
this?".

## Situation

Writing code is no longer the bottleneck. The bottleneck is everything around the change: deciding
what to build, proving it works, getting a person to stand behind it, delivering it and confirming
the result. Agents increase the amount of work that reaches review; they do not increase the number
of people who can approve it.

## Complication

Every tool looks like it solves this because every tool shows an agent doing work. But a turn is not
a change, a patch is not a proof, and a merged PR is not a confirmed result. The market conflates
three different jobs: coordination, build capacity and change delivery with proof.

## Question

What would it take to trust an agent's change enough to ship it, without reading every diff?

## Answer

A vertical lifecycle around the harness: reproduce on the current code, agree the checks, build in a
disposable copy, verify independently, bind the proof to the exact commit, let a person approve the
release, deliver, and confirm the real result.

Works is that lifecycle. It is not a harness and not a horizontal room.

## Three key messages

1. **The bottleneck is trust, not code.** The scarce resource is a person who can approve a change,
   not an agent that can write one.
2. **Works is the change delivery system.** It runs the build through any harness, verifies
   independently, binds the proof to the commit and puts the two human gates on the result; the
   harness stays a harness.
3. **It is not a plugin.** Adding a queue, a policy engine, a verifier, an evidence schema, a gate
   identity and a delivery loop to X changes what X is. That is why the module argument fails on
   ownership and incentives, not on code volume.

## What the audience should do

Ask for a demo or a pilot. Not "nice deck". The deck is successful when someone can repeat the one
line — *harnesses run a turn, Orbit organises work, Works delivers a proven change* — and then ask how to try
it.

## Success criteria

- They can explain why Works is not Orbit and not a harness.
- They can name the two human gates and what each one approves.
- They can say what makes the proof different from a test report.
- They ask about a pilot, an integration or a real repository.

## Non-goals

- A feature tour of every Works screen.
- A roadmap or pricing discussion.
- A claim that Works replaces the harness, the tracker or CI.
- A claim that competitors cannot build this; the argument is that adding it changes their product.

## Open questions

- Internal, partner or customer audience?
- 10 minutes, 20 minutes or a workshop?
- English only, or Russian too?
- Live demo, recorded demo or screenshots only?
- Can we use real task names and real numbers?
- Is Orbit in the room? If yes, the Orbit comparison must be collaborative, not competitive.
