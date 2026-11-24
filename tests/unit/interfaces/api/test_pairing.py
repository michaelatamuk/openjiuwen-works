from __future__ import annotations

from fastapi.testclient import TestClient

from works.interfaces.api.app import create_app

BASE = "http://testserver"


def make_client(paths, *, require_auth: bool = True):
    app = create_app(
        paths,
        writable=True,
        bootstrap_token="bootstrap",  # noqa: S106 - test fixture
        trusted_hosts=("testserver",),
        require_auth=require_auth,
    )
    return TestClient(app, base_url=BASE), app


def issue_device(client: TestClient, token: str, label: str = "phone") -> dict[str, str]:
    started = client.post(
        "/api/v1/admin/pair",
        headers={"Authorization": f"Bearer {token}"},
        json={"label": label},
    )
    assert started.status_code == 200, started.text
    code = started.json()["code"]
    paired = client.post("/api/v1/pair", json={"code": code, "label": label})
    assert paired.status_code == 200, paired.text
    return paired.json()


def test_a_pairing_code_becomes_a_device_token(paths) -> None:
    client, app = make_client(paths)
    with client:
        token = app.state.works.security.token
        paired = issue_device(client, token)

        device = paired["token"]
        assert device.startswith("wd_")
        assert (
            client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {device}"}).status_code
            == 200
        )
        assert (
            client.delete(
                "/api/v1/jobs/j-missing", headers={"Authorization": f"Bearer {device}"}
            ).status_code
            == 404
        )

        devices = client.get(
            "/api/v1/admin/devices", headers={"Authorization": f"Bearer {token}"}
        ).json()["devices"]
        assert devices[0]["label"] == "phone"
        assert "token" not in devices[0]
        assert "token_sha256" not in devices[0]

        revoked = client.delete(
            f"/api/v1/admin/devices/{paired['device_id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert revoked.status_code == 200
        assert (
            client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {device}"}).status_code
            == 401
        )


def test_a_pairing_code_is_one_time_and_expires(paths) -> None:
    client, app = make_client(paths)
    with client:
        token = app.state.works.security.token
        started = client.post(
            "/api/v1/admin/pair",
            headers={"Authorization": f"Bearer {token}"},
            json={"label": "tablet"},
        ).json()
        code = started["code"]
        assert client.post("/api/v1/pair", json={"code": code}).status_code == 200
        assert client.post("/api/v1/pair", json={"code": code}).status_code == 401

        expired = app.state.works.security.pairing_start("old", ttl=-1)
        assert client.post("/api/v1/pair", json={"code": expired["code"]}).status_code == 401


def test_rotating_the_token_revokes_devices(paths) -> None:
    client, app = make_client(paths)
    with client:
        token = app.state.works.security.token
        device = issue_device(client, token)["token"]
        rotated = client.post(
            "/api/v1/admin/rotate-token", headers={"Authorization": f"Bearer {token}"}
        )
        assert rotated.status_code == 200
        new = rotated.json()["token"]
        assert (
            client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {device}"}).status_code
            == 401
        )
        devices = client.get(
            "/api/v1/admin/devices", headers={"Authorization": f"Bearer {new}"}
        ).json()["devices"]
        assert devices == []


def test_loopback_reads_stay_open_without_pairing(paths) -> None:
    client, _ = make_client(paths, require_auth=False)
    with client:
        assert client.get("/api/v1/tasks").status_code == 200


def test_pair_attempts_are_rate_limited(paths) -> None:
    client, _ = make_client(paths)
    with client:
        for _ in range(10):
            assert client.post("/api/v1/pair", json={"code": "nope"}).status_code == 401
        limited = client.post("/api/v1/pair", json={"code": "nope"})
        assert limited.status_code == 429
        assert limited.headers["retry-after"]


def test_devices_expire_and_are_audited(paths) -> None:
    client, app = make_client(paths)
    with client:
        token = app.state.works.security.token
        paired = issue_device(client, token, label="phone")
        security = app.state.works.security
        security._devices[0]["expires_at"] = 0
        security._save_devices()
        expired = client.get(
            "/api/v1/tasks", headers={"Authorization": f"Bearer {paired['token']}"}
        )
        assert expired.status_code == 401

        log = (paths.state / "security.log").read_text(encoding="utf-8")
        assert "pair.start" in log
        assert "pair.success" in log
        assert paired["token"] not in log
