from __future__ import annotations

from fastapi.testclient import TestClient

from works.interfaces.api.app import create_app
from works.interfaces.api.security import COOKIE_NAME

BASE = "http://127.0.0.1"


def make_client(
    paths,
    *,
    writable: bool = True,
    token: str = "bootstrap",  # noqa: S107
):
    app = create_app(paths, writable=writable, bootstrap_token=token)
    return TestClient(app, base_url=BASE), app


def test_bootstrap_token_is_one_time(paths) -> None:
    client, _ = make_client(paths)
    with client:
        first = client.post("/api/v1/session", json={"token": "bootstrap"})
        assert first.status_code == 200
        assert first.json() == {"ok": True}
        assert client.cookies.get(COOKIE_NAME)
        cookie = first.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=strict" in cookie

        second = client.post("/api/v1/session", json={"token": "bootstrap"})
        assert second.status_code == 401
        assert second.json()["error"]["code"] == "auth_error"


def test_session_cookie_authorizes_a_write(paths) -> None:
    client, _ = make_client(paths)
    with client:
        assert client.post("/api/v1/session", json={"token": "bootstrap"}).status_code == 200
        response = client.delete("/api/v1/jobs/j-missing")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_bearer_token_authorizes_a_write(paths) -> None:
    client, app = make_client(paths)
    with client:
        token = app.state.works.security.token
        response = client.delete(
            "/api/v1/jobs/j-missing", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404


def test_write_without_a_token_is_401(paths) -> None:
    client, _ = make_client(paths)
    with client:
        response = client.delete("/api/v1/jobs/j-missing")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "auth_error"


def test_a_paired_device_token_can_start_a_browser_session(paths) -> None:
    client, app = make_client(paths)
    with client:
        token = app.state.works.security.token
        started = client.post(
            "/api/v1/admin/pair",
            json={"label": "phone"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert started.status_code == 200, started.text
        code = started.json()["code"]
        paired = client.post("/api/v1/pair", json={"code": code})
        assert paired.status_code == 200, paired.text
        device_token = paired.json()["token"]

        session = client.post("/api/v1/session", json={"token": device_token})
        assert session.status_code == 200, session.text
        assert client.cookies.get(COOKIE_NAME)
        again = client.post("/api/v1/session", json={"token": "not-a-token"})
        assert again.status_code == 401


def test_read_only_mode_is_403(paths) -> None:
    client, app = make_client(paths, writable=False)
    with client:
        token = app.state.works.security.token
        response = client.delete(
            "/api/v1/jobs/j-missing", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "read_only"


def test_a_foreign_host_is_refused(paths) -> None:
    app = create_app(paths)
    with TestClient(app, base_url="http://evil.test") as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_a_foreign_origin_is_refused(paths) -> None:
    client, _ = make_client(paths)
    with client:
        response = client.post(
            "/api/v1/session",
            json={"token": "bootstrap"},
            headers={"Origin": "http://evil.test"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_rotate_invalidates_the_old_bearer_and_sessions(paths) -> None:
    client, app = make_client(paths)
    with client:
        old = app.state.works.security.token
        session = client.post("/api/v1/session", json={"token": old})
        assert session.status_code == 200
        assert client.cookies.get(COOKIE_NAME)

        rotated = client.post(
            "/api/v1/admin/rotate-token",
            headers={"Authorization": f"Bearer {old}"},
        )
        assert rotated.status_code == 200
        new = rotated.json()["token"]
        assert new != old
        assert (paths.state / "http-token").read_text(encoding="utf-8").strip() == new

        old_write = client.delete(
            "/api/v1/jobs/j-missing", headers={"Authorization": f"Bearer {old}"}
        )
        assert old_write.status_code == 401

        client.cookies.clear()
        cookie_only = client.delete("/api/v1/jobs/j-missing")
        assert cookie_only.status_code == 401

        new_write = client.delete(
            "/api/v1/jobs/j-missing", headers={"Authorization": f"Bearer {new}"}
        )
        assert new_write.status_code == 404
