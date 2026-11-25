# Supply chain and release artifacts

One local product, so the supply-chain work is deliberately small: every artefact a user can install
is built in CI, has a bill of materials and a checksum, and no signing infrastructure is invented
before there is a release process.

## What exists

| Artefact | How it is produced | What proves it |
|---|---|---|
| Wheel | `uv build --wheel` in the `wheel` job | `scripts/check_wheel.py` (the UI bundle and flows are inside), `scripts/smoke_wheel.py` (install + `works --help` + daemon) |
| SBOM | `cyclonedx-py environment` against the `server` extra | `dist/sbom.json` (CycloneDX JSON) uploaded with the wheel |
| Checksums | `sha256sum` in `dist/` | `dist/SHA256SUMS` covers the wheel and the SBOM |
| Python dependencies | `uv.lock` (resolved, frozen in CI) | `uv sync --frozen`; Renovate proposes grouped updates |
| Python advisories | `pip-audit` | the `security` job and the weekly schedule |
| npm advisories | `npm audit --omit=dev` | the `web` job |
| Secrets | `gitleaks` | the `security` job |
| Static analysis | `bandit` | the `security` job |

Reproduce the SBOM locally:

```bash
make sbom          # writes dist/sbom.json
```

## What is deliberately deferred

- **Sigstore/SLSA signing and provenance.** Meaningless without a published release and a key
  custodian; adding a signature nobody verifies is theatre.
- **Reproducible builds.** Hatchling plus Vite hashes are stable enough in practice, but a byte-for-byte
  rebuild has not been proven; it becomes a release task, not a checkbox.
- **MSI/installer and a service wrapper.** The wheel plus Task Scheduler is enough for one home
  (see `docs/guides/runbook.md`); an installer is a product decision.
- **OSV-Scanner.** `pip-audit` + `npm audit` cover the current dependency set; an OSV scan is worth
  adding together with the release pipeline, not before it.
- **Python 3.14 as the primary interpreter.** `openjiuwen` caps at `<3.14`, so the decision waits for
  the provider.

## Verifying a downloaded wheel

```bash
sha256sum -c SHA256SUMS
unzip -p openjiuwen_works-*.whl '*/METADATA' | head -20
```

Then install it into a clean environment and run `works doctor --json`: the `harness` check must name
the providers this build actually ships, not the ones the UI hoped for.

## See also

- `docs/reference/reliability.md` - what the daemon promises after a crash.
- `docs/guides/live-harness.md` - which provider extras exist and why they are optional.
- `docs/adrs/017-remote-trust.md` - the device-token boundary.
