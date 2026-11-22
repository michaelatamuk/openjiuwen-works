"""Resolve a product name to its repository without repeating --repo on every command."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from .config import WorksPaths
from .errors import ConfigError

MAP_PATH = Path(".works") / "products.yaml"


class ProductRepo(BaseModel):
    repo: str


class ProductMap(BaseModel):
    products: dict[str, ProductRepo] = Field(default_factory=dict)


def load_products(paths: WorksPaths) -> ProductMap:
    path = paths.root / MAP_PATH
    if not path.exists():
        return ProductMap()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read {MAP_PATH}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{MAP_PATH} must be a mapping")
    try:
        return ProductMap.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{MAP_PATH} is invalid: {exc}") from exc


def resolve_repo(paths: WorksPaths, product: str, explicit: Path | None = None) -> Path:
    """Explicit --repo wins; otherwise the product map decides; otherwise the CWD."""
    if explicit is not None:
        return explicit.expanduser().resolve()
    map_path = paths.root / MAP_PATH
    if not map_path.exists():
        return Path.cwd().resolve()
    mapping = load_products(paths)
    entry = mapping.products.get(product)
    if entry is None:
        lowered = {name.lower(): value for name, value in mapping.products.items()}
        entry = lowered.get(product.lower())
    if entry is None:
        known = ", ".join(sorted(mapping.products)) or "none"
        raise ConfigError(
            f"product {product!r} has no repository in {MAP_PATH.as_posix()}; "
            f"known products: {known}. Add it there or pass --repo."
        )
    target = Path(entry.repo).expanduser()
    if not target.is_absolute():
        target = paths.root / target
    return target.resolve()
