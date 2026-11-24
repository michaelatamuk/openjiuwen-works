"""HTTP API presenters and runtime helpers."""

from __future__ import annotations

from pathlib import Path

STATIC = {
    "": "index.html",
    "index.html": "index.html",
    "app.css": "app.css",
    "app.js": "app.js",
    "mira.svg": "mira.svg",
}


ASSETS = Path(__file__).resolve().parents[1] / "ui" / "static"


DIST = ASSETS / "dist"


def _dist_asset(name: str) -> Path | None:
    if not DIST.is_dir():
        return None
    if name in ("", "index.html"):
        target = DIST / "index.html"
    elif name.startswith("assets/"):
        target = (DIST / name).resolve()
    else:
        return None
    if DIST.resolve() not in target.parents and target != DIST / "index.html":
        return None
    return target if target.is_file() else None


def _content_type(path: Path) -> str:
    return {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".ico": "image/x-icon",
        ".woff2": "font/woff2",
        ".map": "application/json",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".json": "application/json",
        ".txt": "text/plain; charset=utf-8",
        ".log": "text/plain; charset=utf-8",
        ".trace": "application/json",
    }.get(path.suffix, "application/octet-stream")
