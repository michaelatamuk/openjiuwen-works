from __future__ import annotations

from pathlib import Path

import pytest

from works.application.intake.products import load_products, resolve_repo
from works.domain.errors import ConfigError


def test_product_mapping_resolves_a_repo(paths, tmp_path: Path) -> None:
    target = tmp_path / "blender"
    target.mkdir()
    (paths.root / ".works").mkdir()
    (paths.root / ".works" / "products.yaml").write_text(
        f"products:\n  Blender:\n    repo: {target.as_posix()}\n",
        encoding="utf-8",
    )

    assert resolve_repo(paths, "Blender") == target.resolve()
    assert resolve_repo(paths, "Blender", tmp_path / "other") == (tmp_path / "other").resolve()


def test_an_unmapped_product_names_the_known_products(paths) -> None:
    (paths.root / ".works").mkdir()
    (paths.root / ".works" / "products.yaml").write_text(
        "products:\n  Blender:\n    repo: blender\n", encoding="utf-8"
    )

    with pytest.raises(ConfigError, match="known products: Blender"):
        resolve_repo(paths, "GIMP")


def test_product_names_are_case_insensitive_and_relative(paths) -> None:
    (paths.root / ".works").mkdir()
    (paths.root / ".works" / "products.yaml").write_text(
        "products:\n  Blender:\n    repo: apps/blender\n", encoding="utf-8"
    )

    assert resolve_repo(paths, "blender") == (paths.root / "apps" / "blender").resolve()


def test_no_map_falls_back_to_the_working_directory(paths) -> None:
    assert resolve_repo(paths, "anything") == Path.cwd().resolve()


def test_an_invalid_product_map_is_reported(paths) -> None:
    (paths.root / ".works").mkdir()
    (paths.root / ".works" / "products.yaml").write_text(
        "products: [not, a, map]\n", encoding="utf-8"
    )

    with pytest.raises(ConfigError):
        load_products(paths)


def test_a_non_mapping_file_is_reported(paths) -> None:
    (paths.root / ".works").mkdir()
    (paths.root / ".works" / "products.yaml").write_text("- just\n- a list\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="must be a mapping"):
        load_products(paths)


def test_a_broken_yaml_file_is_reported(paths) -> None:
    (paths.root / ".works").mkdir()
    (paths.root / ".works" / "products.yaml").write_text("products: [unclosed\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="cannot read"):
        load_products(paths)


def test_a_product_entry_needs_a_repo(paths) -> None:
    (paths.root / ".works").mkdir()
    (paths.root / ".works" / "products.yaml").write_text(
        "products:\n  blender:\n    name: Blender\n", encoding="utf-8"
    )

    with pytest.raises(ConfigError, match="invalid"):
        load_products(paths)
