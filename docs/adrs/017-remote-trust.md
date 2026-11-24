# 017 - Remote bind trust model

**Status:** accepted (2026 hardening)

## Context

A local daemon normally listens on loopback. A phone or another computer needs a deliberate,
authenticated remote bind. The remote surface must not turn a local-first tool into an unauthenticated
LAN service.

## Assets

- `.works/state/http-token` (persistent bearer), `devices.json` (hashes only), pairing codes in memory.
- The home: queue events, runs/evidence, ledger, settings.
- The ability to start jobs, approve/release, deliver, deploy and pair devices.

## Adversaries

- An unauthenticated LAN client scanning `0.0.0.0`.
- A stolen phone or a leaked bearer/device token.
- A hostile web origin in the same browser (CSRF/Origin confusion).
- A compromised local account reading token files.
- A resource-exhaustion client opening many SSE streams or huge bodies.

## Controls

- Loopback is the default; `--allow-remote` is explicit and a wildcard bind requires
  `--trusted-host`.
- Every remote API read needs the bearer token or a session cookie; only `/health`, `/health/live`
  and `/session` are open.
- `Host` and `Origin` must match the trusted set; foreign values get `403`.
- Writes require the bearer/session; read-only daemons refuse writes; `require_write` is explicit.
- Pairing codes are high-entropy, one-time, five-minute codes. Device tokens are stored as SHA-256
  hashes, expire after 30 days, can be revoked individually, and are all revoked by token rotation.
- `/pair`, `/session` and `/admin/*` are rate limited; failures return `429` + `Retry-After`.
- Request bodies are capped (declared and chunked); SSE subscribers are capped.
- `http-token`, `devices.json` and the audit log are chmod 600 on POSIX and receive an explicit
  Windows ACL. A remote bind refuses to start when private permissions cannot be established.
- Security events (pair start/success/failure, revoke, rotate) go to an append-only audit log with no
  secrets.
- Logs redact credentials; `pip-audit`/Bandit/Gitleaks run in CI.

## Residual risks and required operations

- The daemon speaks HTTP; remote use needs a tunnel (SSH/Tailscale) or TLS termination. Do not expose
  it to the public internet.
- A tunnel collapses client addresses to loopback, so IP rate limiting is weaker; pairing codes and
  token expiry remain the primary controls.
- A bearer token is a password. Store it in the OS keystore on a native client and rotate it after a
  lost device.
- A compromised local account can read the home; OS account isolation and full-disk encryption are
  outside Works.
- There is no multi-user account model; one home has one trust boundary.

## Consequences

Remote support is opt-in and measurable. A lost device is recoverable in one action, and an
unauthenticated LAN client cannot read evidence or start jobs.
