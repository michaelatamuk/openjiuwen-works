from __future__ import annotations

import argparse

import pytest
from fastapi.testclient import TestClient

from works.domain.errors import ConfigError
from works.interfaces.api.app import create_app
from works.interfaces.cli.commands.daemon import cmd_daemon
from works.interfaces.cli.parser import build_parser


def test_health_matches_the_legacy_shape(paths) -> None:
    app = create_app(paths, writable=True)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["readonly"] is False
    assert body["write"] is True
    assert body["root"] == str(paths.root)
    assert body["version"] == "0.0.1"
    assert isinstance(body["ai"], dict)
    assert isinstance(body["builder"], dict)


def test_read_only_default(paths) -> None:
    app = create_app(paths)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        body = client.get("/api/v1/health").json()

    assert body["readonly"] is True
    assert body["write"] is False


def test_openapi_is_versioned(paths) -> None:
    app = create_app(paths)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "openJiuwen Works"
    assert "/api/v1/health" in response.json()["paths"]


def test_daemon_parser_defaults() -> None:
    args = build_parser().parse_args(["daemon"])
    assert args.host == "127.0.0.1"
    assert args.port == 8765
    assert args.write is False
    assert args.func is cmd_daemon


def test_daemon_refuses_a_remote_bind() -> None:
    args = argparse.Namespace(
        host="192.0.2.1", port=8765, write=False, allow_remote=False, home=None
    )
    with pytest.raises(ConfigError, match="allow-remote"):
        cmd_daemon(args)


def test_request_id_is_echoed_or_generated(paths) -> None:
    app = create_app(paths)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        echoed = client.get("/api/v1/health", headers={"X-Request-ID": "req-123"})
        generated = client.get("/api/v1/health")
    assert echoed.headers["x-request-id"] == "req-123"
    assert generated.headers["x-request-id"]
