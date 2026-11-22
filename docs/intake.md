# Intake: a tracker issue becomes one work item

The engine reads signals from two real trackers and from a person. Every signal lands as the same
kind of task, so nothing downstream knows which tracker it came from.

## Product to repository

`.works/products.yaml` in the Works home maps a product name to its checkout:

```yaml
products:
  firefox:
    repo: C:\src\firefox
  blender:
    repo: C:\src\blender
```

- `works submit --product firefox --ref BUG-7` resolves the repository.
- `--repo` always wins, for an ad-hoc checkout.
- A relative `repo` is resolved against the Works home.
- Names are matched case-insensitively.
- If the map exists but the product is missing, the command fails and lists the known products.
  It never guesses a directory.
- With no map at all, the working directory stays the default (the pre-map behaviour).

## GitHub Issues

```bash
works source github owner/name --product firefox --label bug --limit 20
```

- Reads open issues through the public API; `GITHUB_TOKEN` adds private repositories and a higher
  rate limit.
- Pull requests are skipped (the API returns them in the same list).
- An issue becomes `source.kind=tracker`, `source.ref=owner/name#123`.
- A repeated run returns the same task: deduplication is `(kind, ref)`.

## Jira

```bash
works source jira --url https://jira.example --jql "project = FIRE AND status = Open" \
  --product firefox --limit 20
```

- Needs `JIRA_EMAIL` and `JIRA_TOKEN`; the adapter refuses to run without them.
- An issue becomes `source.kind=tracker`, `source.ref=FIRE-123`.
- The same `(kind, ref)` rule makes the poll idempotent.

## Detector

```bash
works source detector --file alerts.json --product firefox
works source detector --url http://alertmanager:9093/api/v2/alerts --product firefox
works source detector --name prod
```

- Accepts an Alertmanager payload, a generic list, or NDJSON.
- Keeps firing alerts only; resolved alerts are ignored.
- A stable `fingerprint` or `id` is the source ref; a payload without one gets a content hash, so a
  repeated poll returns the same task.
- `DETECTOR_TOKEN` adds a bearer token for a protected endpoint.
- Named detectors live in `.works/detectors.yaml`:

```yaml
detectors:
  prod:
    file: alerts.json
    product: firefox
```

The GUI lists configured detectors and their firing alerts; it does not accept an arbitrary file
path from a browser request.

## Tests and the honest boundary

The HTTP layer is behind a `Transport` callable, so tests use recorded payloads and never touch the
network. What is proven here is parsing, auth headers, refusals and deduplication. A live GitHub or
Jira run needs credentials and is not part of CI.
