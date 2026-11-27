# Documentation

> **Doc status:** active · **Owner:** Michael · **Last reviewed:** 2026-11-27

A page belongs where a reader would look for it, not where its author sits. This page is the rule
for adding, moving and retiring documentation.

## Where a page goes

| Reader's question | Directory | Examples |
|---|---|---|
| What happens, in plain words? | `start/` | the ten stages |
| How do I do this task? | `guides/workflow/` | intake, release, verification |
| How do I run or fix it? | `guides/operations/` | runbook, remote, supply chain |
| How do I connect a harness or service? | `guides/integrations/` | live harness, swarm, PPMA, LAIX |
| What is the contract? | `reference/lifecycle/`, `reference/platform/`, `reference/capabilities/` | stage contracts, HTTP API, scheduler |
| Why is it built this way? | `architecture.md`, `adrs/` | processes, layers, decisions |
| What is planned or delivered? | `roadmap/` | plan, modernization plan, milestones |
| Who is this for? | `strategy/` | positioning, competitors, mascot |
| What did we believe before? | `archive/` | reviews, demos, old proposals |
| Where do images and video live? | `assets/` | UI, deck, frames, the film |

Do not add a new top-level directory without updating this table and `docs/README.md`. Do not create
a directory with a single entry: merge it into a neighbouring section. `make docs` fails on both.

## Every page is registered

`docs/manifest.yaml` is the registry. A page is not done until it has an entry:

```yaml
  - path: docs/guides/workflow/intake.md
    title: "Intake: a tracker issue becomes one work item"
    status: active
    owner: Michael
    last_reviewed: 2026-11-27
    audience: user
    canonical: true
```

- `title` must match the page's first `# ` heading exactly.
- `status` is one of `active`, `legacy`, `archived`, `generated`.
- `owner` is a person, not a team alias.
- `last_reviewed` is the date the content was last checked, not the date the file was touched.
- `audience` is one of `everyone`, `user`, `operator`, `integrator`, `engineer`, `product`.
- `canonical` is `true` when this is the page to read for its subject.

`make docs` fails when a Markdown page is missing from the manifest, an entry points at a missing
file, a title drifts from the heading, a non-active page has no status banner, or a directory holds
a single entry.

## Status

| Status | Meaning | Banner |
|---|---|---|
| `active` | Current; change it when the product changes. | Optional |
| `legacy` | Still authoritative until its replacement lands; do not extend it. | Required |
| `archived` | Historical record; read-only. | Required |
| `generated` | Written by a script; edit the script, not the file. | Required |

A non-active page starts with a banner directly under the H1:

```markdown
> **Doc status:** legacy · **Owner:** Michael · **Last reviewed:** 2026-11-21
```

The banner must agree with the manifest. A page whose status changes gets both edits in one commit.

## Add a page

1. Put the file in the directory that matches the reader's question.
2. Add the H1 and the body. Use the stage template below for a lifecycle contract.
3. Add the manifest entry.
4. Add a banner if the status is not `active`.
5. Link it from `docs/README.md` and from the nearest section page.
6. Run `make docs`.

## Move or retire a page

- Move with `git mv` and update every relative link; `make docs-links` catches the rest.
- Change the manifest `path` in the same commit.
- Retire by moving to `archive/`, setting `status: archived`, adding the banner, and removing it
  from current navigation. Never delete a decision record; supersede it.
- A redirect page is not used. Fix the link instead.

## Stage template

```markdown
# Stage name (stage N)

> **Doc status:** active · **Owner:** Michael · **Last reviewed:** YYYY-MM-DD

One sentence: the guarantee this stage makes.

## Inputs

What must exist before the stage starts.

## Outputs

What the stage writes, and where.

## Contract

The commands, routes, files and invariants another stage may rely on.

## Failure modes

What the operator sees, why it happens, and the first response.

## Evidence

What is hashed or recomputed, and how to re-check it.

## Related

Links to the stage before, the stage after, the ADR and the guide.
```

## Decisions and generated files

- An architecture decision is `docs/adrs/NNN-slug.md`, using the same context / decision /
  consequences / alternatives structure. Add it to the table in `docs/adrs/README.md`; the index
  check fails on a missing or misnumbered row.
- A generated file is never edited by hand. `docs/reference/generated/README.md` names the script
  and the check for each one.
- `docs/archive/` is read-only. New history goes there only after the current page exists.
