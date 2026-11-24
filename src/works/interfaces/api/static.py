"""Small HTTP helpers shared by the API presenters."""

from __future__ import annotations

from pathlib import Path


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
