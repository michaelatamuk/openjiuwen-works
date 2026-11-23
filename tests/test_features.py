from __future__ import annotations

from pathlib import Path

from works.application.observability.features import feature_summary, load_feature_maps


def _repo(tmp_path: Path, body: str) -> Path:
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "demo.yaml").write_text(body, encoding="utf-8")
    return tmp_path


def test_a_feature_map_is_loaded_and_checked_against_the_proof(tmp_path) -> None:
    repo = _repo(
        tmp_path,
        """
schema_version: 1
product: demo
features:
  - id: add-two-numbers
    name: Add two numbers
    user_path: A person calls add(2, 3)
    expected: The result is 5
    scenario_ids: [add-positive, add-negative]
  - id: material-preview
    name: Material preview
    user_path: A person switches to material preview
    expected: The preview does not flicker
    selector: "[data-preview=material]"
""",
    )
    evidence = {
        "verdict": {
            "outcomes": [
                {"id": "add-positive", "passed": True},
                {"id": "add-negative", "passed": False},
            ]
        }
    }

    maps = load_feature_maps(repo)
    summary = feature_summary(repo, evidence)

    assert maps[0].product == "demo"
    assert summary["total"] == 2
    assert summary["covered"] == 1
    assert summary["passed"] == 0
    assert summary["uncovered"] == 1
    assert summary["features"][0]["scenarios"] == ["add-positive", "add-negative"]


def test_a_missing_map_is_explicit(tmp_path) -> None:
    summary = feature_summary(tmp_path)

    assert summary["available"] is False
    assert "No feature map" in summary["note"]


def test_an_invalid_map_is_reported_not_hidden(tmp_path) -> None:
    repo = _repo(
        tmp_path,
        """
schema_version: 1
product: demo
features:
  - id: broken
    name: Broken
    user_path: nowhere
    expected: nothing
""",
    )

    summary = feature_summary(repo)

    assert summary["available"] is True
    assert summary["features"] == []
    assert "invalid" in summary["error"]
