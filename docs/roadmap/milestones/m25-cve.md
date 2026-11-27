# M25 — CVE intake (design)

> **Doc status:** archived · **Owner:** Michael · **Last reviewed:** 2026-11-26

Status: complete (25.1–25.5).

## Why

A CVE is the cheapest kind of report to act on: the package, the affected range and the fixed release
are already written down. Today those reports arrive only if a person files one. For the regulated
buyer this product targets, "we scan the lockfile and open a proven fix per advisory" is the shortest
path from a feed to an auditable change.

## Decision

**Offline first.** A scan reads an OSV-style JSON file by default: deterministic, reviewable before it
touches the queue, and testable in CI without a network. `--osv` queries the batch API as an explicit
opt-in; a failed request is a clear configuration error, never a silent empty result.

**The advisory travels with the change.** The hit becomes a task with `Source.advisory`; the proof
copies it into `Evidence.advisory`. The page then names the CVE, the package, the pinned version and
the fixed release next to the checks that prove the upgrade.

**No invented reproduction.** The advice is "upgrade `pkg` from `1.2.0` to `1.4.2` and run the
repository checks". M25 does not claim to run an exploit or a PoC. Reproduction stays the existing
stage, with the repository's own tests.

## What is read

| file | ecosystem |
|---|---|
| `uv.lock`, `poetry.lock` | PyPI |
| `requirements.txt`, `requirements-dev.txt`, `requirements-prod.txt` | PyPI |
| `package-lock.json` (v2/v3 `packages`, v1 `dependencies`) | npm |

Pins only: `name==version`, `[[package]]` entries and lockfile package versions. Ranges, extras and
environment markers are not resolved; a repository without a lockfile has nothing to scan and says so.

## Matching

- Names are normalised (`Demo_Pkg`, `zope.interface` and `demo-pkg` are the same pin).
- An advisory matches a pin when the ecosystem agrees and either the version is listed explicitly, or
  it falls inside an OSV range: `introduced <= version < fixed`, or `introduced <= version <=
  last_affected`.
- PyPI versions use PEP 440 (`packaging`); npm versions use a numeric `major.minor.patch` comparison.
  A version that cannot be parsed falls back to text comparison and is reported as such in the tests.

## Severity

| advisory | task |
|---|---|
| critical | S1 |
| high | S2 |
| moderate / medium | S3 |
| low | S4 |
| unknown | S3 |

The mapping only orders the queue; it does not change a gate.

## Evidence

- `Evidence.advisory` carries the id, package, version, severity, fixed release, CVSS and up to a few
  links. It is written before `bind()`, so it is covered by `proof_sha256`.
- Old proofs have no advisory; `bind()` excludes the field when it is absent, so their hash does not
  change.
- `evidence.md` gains an **Advisory** section; the plain-language summary names the advisory in the
  first sentence.
- The UI shows an **Advisory** card with the same fields.

## Limits

- No transitive resolution beyond the lockfile, no floating ranges, no environment markers.
- No PoC or exploit execution; the repository's checks prove the upgrade.
- npm comparison ignores prerelease ordering; a range that depends on it may need a manual look.
- No automatic upgrade, no automatic release; the two gates still apply.
- No Jira or Linear feed, no scheduled poller yet — the scan is an explicit command.

## Acceptance

| case | test |
|---|---|
| OSV record expands to a CVE, severity and range | `test_an_osv_record_expands_to_its_cve_and_range` |
| wrapper, list and single-record feeds | `test_a_feed_accepts_a_wrapper_a_list_and_a_single_record` |
| requirements, uv.lock, package-lock parsing | `test_*lock*`, `test_requirements_keep_pins_and_ignore_ranges` |
| introduced/fixed boundaries, npm ordering | `test_ranges_include_and_exclude_the_right_versions`, `test_npm_versions_compare_numerically` |
| one task per CVE × package@version, dedupe | `test_a_scan_creates_one_task_per_package_and_version`, `test_a_second_scan_finds_the_existing_task` |
| advisory rendered, bound, old hash preserved | `test_the_advisory_is_rendered_and_bound`, `test_an_old_proof_keeps_its_hash_without_an_advisory` |
| OSV batch client | `test_osv_fetch_parses_a_batch` |
| CLI scan | `test_a_cli_scan_reports_and_creates` |

## Work breakdown

| item | days |
|---|---|
| 25.1 feed parsing and the OSV batch client | 1 |
| 25.2 lockfile readers | 0.7 |
| 25.3 matching, severity and task submission | 0.8 |
| 25.4 advisory in the evidence, summary and UI | 0.7 |
| 25.5 CLI, docs and tests | 0.8 |
| **total** | **4 (~5 with contingency)** |
