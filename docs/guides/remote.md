# Remote clients and the LAN

The daemon is loopback-only by default. That is the safe deployment: reads are open on
`127.0.0.1`, writes need the local bearer or a session cookie, and Host/Origin must match loopback.

A native Windows app on the same machine is a loopback client. A phone or another computer is a
remote client and needs an explicit, authenticated bind.

## Bind one address, not the world

```bash
uv sync --extra server
works --home /path/to/workspace daemon start --write \
  --host 0.0.0.0 --allow-remote \
  --trusted-host 192.168.1.20
```

- `--allow-remote` is required for a non-loopback address.
- A wildcard bind (`0.0.0.0`/`::`) requires at least one `--trusted-host`; the daemon refuses to
  guess which address clients use.
- Every `Host` header must be in the trusted set; foreign hosts and foreign `Origin` values get
  `403`. Repeat `--trusted-host` for several names (LAN IP, Tailscale name).
- On a remote bind **all API reads require auth** (the bearer token or a session cookie). Only
  `/api/v1/health` and `/api/v1/session` stay open, so a client can discover the daemon and exchange
  a token.

The token is `.works/state/http-token`. Treat it as a password; rotate it with
`POST /api/v1/admin/rotate-token` (authenticated). A native client stores it in the OS keystore.

## Prefer a tunnel to a public bind

Do not expose the daemon to the internet. The supported patterns are:

- an SSH local forward (`ssh -L 8765:127.0.0.1:8765 host`) and a loopback daemon;
- Tailscale/WireGuard, with the tailnet name in `--trusted-host`;
- TLS termination in front of the daemon if the network is not trusted. The daemon itself speaks
  HTTP on loopback or a private address.

A browser on the same trusted host can use the bootstrap URL and the HttpOnly session cookie. A
native app should send `Authorization: Bearer <token>`; it does not need CORS. A second browser
origin would need an explicit CORS decision, which is not enabled today.

## Phone paths

- Emulator: the host loopback is `10.0.2.2`; add `--trusted-host 10.0.2.2` (or bind the host and
  use its LAN address).
- Physical device: bind the LAN address and trust the address the phone uses.
- The phone never runs git, worktrees or subprocesses. It calls `/api/v1`, receives job ids and
  reads the SSE stream; the desktop daemon performs the work.

Pair a phone with `works daemon pair --label phone`; enter the printed code on the device at
`POST /api/v1/pair` (or the Settings surface). The daemon stores only a SHA-256 hash of the device
token, the code expires after five minutes, and devices expire after 30 days. Revoke a lost device
with `DELETE /api/v1/admin/devices/<id>` or the Settings device list. Rotating the daemon token
revokes every device at once.
