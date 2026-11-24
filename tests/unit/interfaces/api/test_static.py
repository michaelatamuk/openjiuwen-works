from __future__ import annotations

from fastapi.testclient import TestClient

from works.interfaces.api.app import DIST, create_app

BASE = "http://127.0.0.1"


def test_the_spa_and_its_assets_are_served(paths) -> None:
    app = create_app(paths)
    bundle = next((DIST / "assets").glob("*.js"))
    with TestClient(app, base_url=BASE) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert 'id="root"' in root.text

        deep = client.get("/task/t-demo/story")
        assert deep.status_code == 200
        assert 'id="root"' in deep.text

        asset = client.get(f"/assets/{bundle.name}")
        assert asset.status_code == 200
        assert len(asset.content) > 1000

        mascot = client.get("/mira.svg")
        assert mascot.status_code == 200
        assert mascot.headers["content-type"].startswith("image/svg")


def test_unknown_api_paths_stay_json_404(paths) -> None:
    app = create_app(paths)
    with TestClient(app, base_url=BASE) as client:
        response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
