# CVE intake

A CVE is a report with the package, the affected range and the fixed release already written down.
M25 turns those into tasks without inventing a reproduction.

## Scan

```bash
works cve scan --repo ../service --feed advisories.json
works cve scan --repo ../service --osv --product openjiuwen --json
```

- `--feed` reads an OSV-style JSON file; the scan is offline and deterministic.
- `--osv` sends the pinned packages to `api.osv.dev` in one batch. A network failure is a
  `config_error`, not an empty result.
- The command prints every hit, then the task ids it created and the ones already queued.

A feed may be a single OSV record, a list of records, or `{"vulns": [...]}`. The GitHub advisory
database and the OSV API both fit.

## Lockfiles

| file | ecosystem |
|---|---|
| `uv.lock`, `poetry.lock` | PyPI |
| `requirements*.txt` | PyPI |
| `package-lock.json` | npm |

Only pins are read. A repository without one of these files has nothing to scan.

## Matching

Names are normalised (`Demo_Pkg` = `demo-pkg`). A pin matches when the ecosystem agrees and either the
version is listed in the advisory or it falls inside an OSV range:

- `introduced <= version < fixed`;
- `introduced <= version <= last_affected`.

PyPI uses PEP 440; npm uses a numeric `major.minor.patch` comparison. Prerelease ordering is not
modelled.

## What the task carries

- `ref`: the CVE id when the advisory has one, otherwise the advisory id;
- `severity`: critical → S1, high → S2, moderate/medium → S3, low → S4, unknown → S3;
- labels `security`, `cve`, `ecosystem:<pypi|npm>`;
- a reproduction hint: upgrade the package and run the repository checks;
- a dedupe key `cve:<id>:<package>@<version>`, so a second scan finds the same task;
- `advisory` with the package, version, fixed release, CVSS and links.

## Evidence

`Evidence.advisory` is written before binding and is covered by `proof_sha256`. The proof page gains an
**Advisory** section, the plain-language summary names the advisory in its first sentence, and the UI
shows an **Advisory** card. Proofs written before M25 keep their hash: the field is excluded when it is
absent.

## Not claimed

- No exploit or PoC is executed; the repository's checks prove the upgrade.
- No transitive resolution beyond the lockfile, no floating ranges, no environment markers.
- No automatic upgrade, release or close; the two human gates are unchanged.
- No scheduled poller and no Jira/Linear feed yet.
