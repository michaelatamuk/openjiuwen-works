# Signal intake (stage 1)

A signal is more than a title. This page covers the four ways work enters Works and the rules that
keep the queue honest.

## What a signal carries

`Source` fields beyond `kind`, `ref` and `title`: `severity` (S1–S4), `labels`, `links`, `author`,
`channel`, `reproduction_hint`, `received_at` and `dedupe_key`. `dedupe_key` is the identity used for
duplicate detection; it falls back to `ref`, so tasks created before the field existed keep their ids.

## Sources and the registry

`<home>/.works/sources.json` lists each source: `enabled`, `product`, optional local `repo`, the
secret environment variable and `limit_per_minute`. Defaults are `github` and `generic`.

```bash
works sources list
works sources enable github
works sources disable generic
```

`GET /api/v1/sources` returns the same registry with accepted/duplicate/rejected counters.

## Webhooks

```text
POST /api/v1/hooks/{source}
X-Hub-Signature-256: sha256=…      (GitHub)   or   X-Works-Signature: sha256=…
X-GitHub-Delivery: <uuid>          (replay protection)
```

- The HMAC is checked over the raw body against `WORKS_WEBHOOK_SECRET_<SOURCE>`; a mismatch is `401`
  and writes an audit line, not a task.
- A delivery id seen before returns `200 {"duplicate": true}`.
- Over `limit_per_minute` returns `429`.
- A disabled source returns `403`, an unknown one `404`, an unset secret `503`.
- A `github` payload is an issues event, or an `issue_comment` on a released task
  (see `reporter.md`); a `generic` payload is `{ref, title, …}`.
- Every attempt is appended to `state/webhooks.jsonl`; counters live in
  `state/webhook-metrics.json`.

## MCP

```bash
python -m works.mcp_server [--home PATH]
```

Tools: `submit_signal`, `list_tasks`, `get_task`, `get_evidence`, `get_release_packet`. There is no
tool that approves a plan, opens a release gate or edits evidence — a person still owns both gates.

## Triage

`GET /api/v1/inbox` groups non-terminal tasks by a normalised title. `POST /tasks/{id}/merge`
`{"into": "<task-id>"}` appends `task.merged` and moves the duplicate to `blocked`; history is never
deleted. The Queue sidebar shows up to three groups with a Merge button. `POST /inbox/mute`
`{"source": "github"}` disables the source in the registry.

## Reproduction hint

`reproduction_hint` is stored on the task and copied into evidence, where `evidence.md` shows a
**Reproduction hint** line. It is advice for stage 2: it is not executed automatically, because the
text comes from an untrusted source.
