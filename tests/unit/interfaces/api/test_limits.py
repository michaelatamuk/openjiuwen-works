from __future__ import annotations

from collections.abc import Iterator

from fastapi.testclient import TestClient

from works.interfaces.api.app import create_app

BASE = "http://127.0.0.1"


def make_client(paths, *, limit: int = 64):
    app = create_app(
        paths,
        writable=True,
        bootstrap_token="bootstrap",  # noqa: S106 - test fixture
        max_body_bytes=limit,
    )
    client = TestClient(app, base_url=BASE)
    return client, app


def test_a_declared_body_over_the_limit_is_413(paths) -> None:
    client, app = make_client(paths, limit=16)
    with client:
        token = app.state.works.security.token
        response = client.post(
            "/api/v1/tasks",
            headers={"Authorization": f"Bearer {token}"},
            content=b"x" * 100,
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_a_chunked_body_over_the_limit_is_413(paths) -> None:
    client, app = make_client(paths, limit=16)

    def chunks() -> Iterator[bytes]:
        yield b"x" * 10
        yield b"y" * 20

    with client:
        token = app.state.works.security.token
        response = client.post(
            "/api/v1/tasks",
            headers={"Authorization": f"Bearer {token}"},
            content=chunks(),
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_a_small_body_reaches_the_route(paths) -> None:
    client, _ = make_client(paths)
    with client:
        response = client.post("/api/v1/tasks", content=b"{}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_error"
