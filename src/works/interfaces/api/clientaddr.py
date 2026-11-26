"""Who is calling: loopback or a remote client."""

from __future__ import annotations

from fastapi import Request

LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def is_remote(request: Request) -> bool:
    client = request.client
    return client is None or client.host not in LOOPBACK
