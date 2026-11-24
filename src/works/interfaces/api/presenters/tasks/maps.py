"""Product and detector maps for the queue sidebar."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from works.application.intake.detectors import alerts_for, load_config
from works.application.intake.products import MAP_PATH, load_products
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError


def product_map(paths: WorksPaths) -> dict[str, Any]:
    mapping = load_products(paths)
    items: list[dict[str, Any]] = []
    for name, entry in sorted(mapping.products.items()):
        repo = Path(entry.repo).expanduser()
        if not repo.is_absolute():
            repo = paths.root / repo
        repo = repo.resolve()
        items.append(
            {
                "name": name,
                "repo": str(repo),
                "exists": repo.is_dir(),
                "git": (repo / ".git").exists(),
            }
        )
    return {
        "path": MAP_PATH.as_posix(),
        "configured": bool(items),
        "products": items,
    }


def detector_map(paths: WorksPaths, *, refresh: bool = False) -> dict[str, Any]:
    config = load_config(paths)
    items: list[dict[str, Any]] = []
    for name, source in sorted(config.detectors.items()):
        alerts: list[dict[str, Any]] = []
        error: str | None = None
        if source.file or refresh:
            try:
                alerts = [
                    {
                        "ref": alert.ref,
                        "title": alert.title,
                        "severity": alert.severity,
                        "status": alert.status,
                    }
                    for alert in alerts_for(paths, name)
                ]
            except ConfigError as exc:
                error = str(exc)
        items.append(
            {
                "name": name,
                "product": source.product,
                "file": source.file,
                "url": source.url,
                "alerts": alerts,
                "error": error,
                "needs_refresh": bool(source.url and not refresh),
            }
        )
    return {"path": ".works/detectors.yaml", "configured": bool(items), "detectors": items}
