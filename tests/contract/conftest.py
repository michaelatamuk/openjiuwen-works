from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from scripts.seed_home import DEFAULT_NOW, seed

from works.interfaces.api.app import create_app


@pytest.fixture(scope="session")
def seeded_home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("contract-home") / "home"
    seed(root, now=DEFAULT_NOW)
    return root


@pytest.fixture(scope="session")
def client(seeded_home: Path) -> Iterator[TestClient]:
    app = create_app(seeded_home)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client
