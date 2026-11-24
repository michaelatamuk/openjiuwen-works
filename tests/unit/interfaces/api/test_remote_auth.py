from __future__ import annotations

from argparse import Namespace

import pytest
from fastapi.testclient import TestClient

from works.domain.errors import ConfigError
from works.interfaces.api.app import create_app
from works.interfaces.cli.commands.daemon import _trusted_hosts

BASE = "http://testserver"


def test_remote_reads_need_the_bearer_or_a_session(paths) -> None:
    app = create_app(
        paths,
        writable=False,
        trusted_hosts=("testserver",),
        require_auth=True,
    )
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/api/v1/health").status_code == 200

        anonymous = client.get("/api/v1/tasks")
        assert anonymous.status_code == 401
        assert anonymous.json()["error"]["code"] == "auth_error"

        token = app.state.works.security.token
        bearer = client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {token}"})
        assert bearer.status_code == 200

        session = client.post("/api/v1/session", json={"token": token})
        assert session.status_code == 200
        cookie_read = client.get("/api/v1/tasks")
        assert cookie_read.status_code == 200


def test_loopback_reads_stay_open(paths) -> None:
    app = create_app(paths, writable=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/v1/tasks").status_code == 200


def test_a_wildcard_bind_needs_an_explicit_trusted_host() -> None:
    with pytest.raises(ConfigError, match="trusted-host"):
        _trusted_hosts(Namespace(host="0.0.0.0", trusted_host=None))  # noqa: S104

    trusted = _trusted_hosts(
        Namespace(host="0.0.0.0", trusted_host=["192.168.1.20"])  # noqa: S104
    )
    assert "192.168.1.20" in trusted
    assert "127.0.0.1" in trusted
