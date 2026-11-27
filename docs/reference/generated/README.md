# Generated reference

> **Doc status:** generated · **Owner:** Michael · **Last reviewed:** 2026-11-27

The files in this directory are written by scripts. Do not edit them by hand; change the code or
the script and regenerate.

| File | Written by | Checked by |
|---|---|---|
| [`openapi.json`](openapi.json) | `uv run python scripts/dump_openapi.py --update` | `uv run python scripts/dump_openapi.py --check` |
| [`openapi.baseline.json`](openapi.baseline.json) | copied from `openapi.json` when a breaking change is deliberate | `uv run python scripts/check_api_compat.py docs/reference/generated/openapi.baseline.json docs/reference/generated/openapi.json` |
| [`typing-baseline.json`](typing-baseline.json) | `uv run python scripts/check_typing_ratchet.py --update` | `uv run python scripts/check_typing_ratchet.py` |

`make docs` checks the Markdown structure; `make api-compat`, `make routes` and
`make typing-ratchet` check the generated contracts.
