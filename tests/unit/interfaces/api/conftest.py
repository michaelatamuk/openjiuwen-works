from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from scripts.seed_home import DEFAULT_NOW, seed

from works.interfaces.api.app import create_app


@pytest.fixture(scope="module")
def seeded_home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("api-home") / "home"
    seed(root, now=DEFAULT_NOW)
    return root


@pytest.fixture(scope="module")
def seeded_app(seeded_home: Path):
    return create_app(
        seeded_home,
        writable=True,
        bootstrap_token="bootstrap",  # noqa: S106 - test fixture
    )


@pytest.fixture(scope="module")
def seeded_client(seeded_app) -> Iterator[TestClient]:
    with TestClient(seeded_app, base_url="http://127.0.0.1") as client:
        yield client


@pytest.fixture(scope="module")
def auth(seeded_client: TestClient) -> dict[str, str]:
    token = seeded_client.app.state.works.security.token
    return {"Authorization": f"Bearer {token}"}
