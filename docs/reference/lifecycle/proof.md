# Proof (stage 7)

> **Doc status:** active · **Owner:** Michael · **Last reviewed:** 2026-11-27

A proof is a page plus the material to re-check it. Nothing here is decorative: every claim is either
hashed or recomputed.

## Verify

```bash
works proof verify <run-id>
```

Recomputes:

- the diff hash against `diff_sha256`;
- the proof fingerprint from the page itself;
- every artifact's sha256 against the file in the run directory;
- the event root against the recorded event range.

A tampered diff, a changed artifact, an edited page or a removed event makes it fail with the failing
check named. `evidence.md` is a rendering; `evidence.json` is the proof.

## Event chain

`event_root` is a rolling SHA-256 over the run's events (sequence, time, type, data and the previous
hash), capped at `event_seq`. Removing or editing an event changes the root, and `verify` reports it.

## Diff

`evidence.json` keeps the full diff; `evidence.md` truncates it with a visible note and points to the
JSON. Binary files and renames appear as git writes them.

## Plain-language summary

Every new run writes `artifacts/summary.md`: five sections — what was wrong, what caused it, what
changed, what proves it and what was not tested — rendered by a deterministic template from the same
record. It makes no model call, invents no number and names a missing field as missing. The text is
stored in `evidence.json`, covered by `proof_sha256`, and its file hash is an artifact.

```bash
works proof summary <run-id>
works proof summary <run-id> --json
```

The JSON form returns `{text, sha256, derived}`. Records written before M23 have no stored summary:
one is derived on read and marked `derived`, and the original proof hash is never rewritten.

## Risk

`evidence.json` carries a `RiskRating`: the level, one-line reasons, owners, required reviewers, file
and line counts, the largest file's churn, the number of files over 200 changed lines and the matched
security-sensitive paths. A path in the flow's `risk.high_paths` or `risk.sensitive_paths` raises the
tier to high and names an owner. The rating is written before the fingerprint, so editing it later
breaks `works proof verify`. The rating never approves or bypasses a gate; the owner still decides.

## Redaction

Command tails and the builder transcript are scanned for credential shapes (provider keys, GitHub
tokens, AWS keys, `token=…`) and replaced with `[redacted]`; the page lists how many places were
redacted. The diff itself is kept intact because delivery applies it; a secret committed in code is a
code review problem, not something the proof may silently rewrite.

## Reproducibility

The page records the Python version, platform, adapter version and schema version, plus the existing
commit, checks hash, scenario hash, prompt hash, model and provider. Old pages without the newer fields
still load with defaults.

## Export and compare

```bash
works proof export <run-id> [--out proof.tar.gz]
works proof diff <run-a> <run-b>
```

The export is a tarball with a `manifest.json` of file hashes. The diff reports verdict, risk, tokens,
USD, changed files and whether the fingerprint moved.

## Not claimed

No signing, no blockchain, no timestamp authority. Those wait for a real publish process; a signature
nobody verifies is theatre.
