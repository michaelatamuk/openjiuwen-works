# Duplicate suggestions (inbox triage)

The same problem often arrives twice: a webhook, a tracker import and a pasted link with different
refs. The inbox proposes groups; it never merges anything by itself.

## Grouping

- only non-terminal tasks;
- key = the title lowercased with punctuation collapsed (`add SUBTRACTS!` → `add subtracts`);
- a group needs at least two tasks and a key of at least a few characters;
- each group carries a `reason` and a `signature` over its member ids.

The rule is intentionally simple and can over-group generic titles ("fix bug"). Treat the suggestion as
a hint, not a verdict.

## What the UI shows

Each group lists **every member** (id, title, source), a target radio (default: the oldest), the
consequence ("keep X; N duplicates become blocked; history is kept") and two actions:

- **Merge N into X** — merges each other member into the chosen target;
- **Not duplicates** — remembers the group `signature` and hides the suggestion.

A new member changes the signature, so a dismissal does not hide a genuinely new duplicate later.

## API

| method | path | meaning |
|---|---|---|
| GET | `/api/v1/inbox` | duplicate groups and gate reminders |
| POST | `/api/v1/tasks/{id}/merge` | `{"into": "<target>"}`; records `task.merged`, blocks the duplicate |
| POST | `/api/v1/inbox/dismiss` | `{"signature": "..."}`; persists "not duplicates" |
| POST | `/api/v1/inbox/mute` | disables a source in the registry |

Merging never deletes history: the duplicate keeps its events and becomes `blocked`; the target is
unchanged. The target must not be terminal.

CLI equivalent: `works task <duplicate> --merge-into <target>`.

Dismissals live in `state/inbox-dismissed.json` (last 200 signatures).
