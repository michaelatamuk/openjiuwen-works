"""Capture canonicalized API responses from the FastAPI app.

The fixtures are the safety net for the FastAPI migration: every read endpoint is recorded from a
seeded home, with ids, timestamps, hashes and absolute paths masked.

    python scripts/capture_api_fixtures.py --check
    python scripts/capture_api_fixtures.py --update
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

FACTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY))

from fastapi.testclient import TestClient  # noqa: E402
from scripts.seed_home import DEFAULT_NOW, seed  # noqa: E402
from tests.contract.canonicalize import canonicalize  # noqa: E402

from works.interfaces.api.app import create_app  # noqa: E402

FIXTURES = FACTORY / "tests" / "contract" / "fixtures"


def _get(client: TestClient, path: str) -> Any:
    response = client.get(f"/api/v1{path}")
    response.raise_for_status()
    return response.json()


def _stable_health(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": payload.get("ok"),
        "readonly": payload.get("readonly"),
        "write": payload.get("write"),
        "root": payload.get("root"),
        "version": payload.get("version"),
        "has_ai": isinstance(payload.get("ai"), dict),
        "has_builder": isinstance(payload.get("builder"), dict),
    }


def _slug(ref: str) -> str:
    raw = "".join(character if character.isalnum() else "-" for character in ref.lower())
    return raw.strip("-")


def capture(home: Path) -> dict[str, Any]:
    app = create_app(home)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        tasks = _get(client, "/tasks?limit=200")
        task_ids = [task["id"] for task in tasks.get("tasks", [])]
        fixtures: dict[str, Any] = {
            "health": _stable_health(_get(client, "/health")),
            "products": _get(client, "/products"),
            "detectors": _get(client, "/detectors"),
            "tasks": tasks,
            "metrics": _get(client, "/metrics"),
            "ledger": _get(client, "/ledger"),
        }
        for task in tasks.get("tasks", []):
            slug = _slug(str(task["source"]).split(":", 1)[-1])
            fixtures[f"task-{slug}"] = _get(client, f"/tasks/{task['id']}")
            fixtures[f"runs-{slug}"] = _get(client, f"/tasks/{task['id']}/runs")
        if not task_ids:
            raise SystemExit("the seed home has no tasks")
        return fixtures


def _canonical(fixtures: dict[str, Any], home: Path) -> dict[str, Any]:
    repo = home / "repo"
    return {name: canonicalize(payload, home=home, repo=repo) for name, payload in fixtures.items()}


def _write(fixtures: dict[str, Any], target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name, payload in fixtures.items():
        (target / f"{name}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def _compare(fixtures: dict[str, Any], target: Path) -> list[str]:
    problems: list[str] = []
    for name, payload in fixtures.items():
        path = target / f"{name}.json"
        if not path.exists():
            problems.append(f"missing {path.relative_to(FACTORY)}")
            continue
        expected = json.loads(path.read_text(encoding="utf-8"))
        if expected != json.loads(json.dumps(payload)):
            problems.append(f"differs {path.relative_to(FACTORY)}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=None)
    parser.add_argument("--update", action="store_true", help="rewrite the committed fixtures")
    parser.add_argument("--check", action="store_true", help="fail when fixtures differ")
    args = parser.parse_args()

    root = args.home
    temporary: Path | None = None
    if root is None:
        temporary = Path(tempfile.mkdtemp(prefix="works-contract-"))
        root = temporary / "home"
    root = root.expanduser().resolve()
    if root.exists():
        shutil.rmtree(root)
    seed(root, now=DEFAULT_NOW)
    try:
        fixtures = _canonical(capture(root), root)
        if args.update:
            _write(fixtures, FIXTURES)
            print(f"wrote {len(fixtures)} fixtures to {FIXTURES.relative_to(FACTORY)}")
        else:
            problems = _compare(fixtures, FIXTURES)
            if problems:
                for problem in problems:
                    print(problem)
                raise SystemExit(1)
            print(f"{len(fixtures)} fixtures match")
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    main()
