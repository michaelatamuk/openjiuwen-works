"""Local write authentication.

Reads are open on loopback; writes need either the persistent bearer token (CLI) or an HttpOnly
session cookie created from a one-time bootstrap token (`works ui`).
"""

from __future__ import annotations

import contextlib
import getpass
import hashlib
import hmac
import json
import os
import secrets
import subprocess  # nosec B404
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import Request

from works.adapters.queue.atomic import atomic_write
from works.config.paths import WorksPaths
from works.domain.errors import AuthError, ReadOnlyError

COOKIE_NAME = "works_session"
CREDENTIAL_FILE = "http-token"
DEVICES_FILE = "devices.json"
PAIRING_TTL = 300.0
DEVICE_PREFIX = "wd_"
DEVICE_TTL = 30 * 24 * 60 * 60
AUDIT_FILE = "security.log"


class Security:
    def __init__(self, paths: WorksPaths, *, bootstrap_token: str | None = None) -> None:
        self._token_path = paths.state / CREDENTIAL_FILE
        self._devices_path = paths.state / DEVICES_FILE
        self._token = self._load_or_create()
        self._bootstrap = bootstrap_token or secrets.token_urlsafe(24)
        self._sessions: set[str] = set()
        self._devices: list[dict[str, Any]] = self._load_devices()
        self._pairings: dict[str, dict[str, Any]] = {}
        self._audit_path = paths.state / AUDIT_FILE
        self._audit_lock = threading.Lock()
        self._permissions_ok = self._harden(self._token_path)
        self._harden(self._devices_path)
        self._harden(self._audit_path)

    @property
    def token(self) -> str:
        return self._token

    @property
    def permissions_ok(self) -> bool:
        return self._permissions_ok

    @property
    def bootstrap_token(self) -> str:
        return self._bootstrap

    @staticmethod
    def _harden(path: Path) -> bool:
        if os.name == "nt":
            user = os.environ.get("USERNAME") or os.environ.get("USER")
            if not user:
                try:
                    user = getpass.getuser()
                except Exception:  # pragma: no cover - environment without an identity
                    return False
            result = subprocess.run(  # noqa: S603  # nosec B603 B607
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],  # noqa: S607
                capture_output=True,
                check=False,
            )
            return result.returncode == 0
        try:
            os.chmod(path, 0o600)
        except OSError:
            return False
        return True

    def _audit(self, event: str, **fields: Any) -> None:
        payload = {"ts": time.time(), "event": event, **fields}
        with self._audit_lock:
            with self._audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._harden(self._audit_path)

    def _load_or_create(self) -> str:
        if self._token_path.exists():
            existing = self._token_path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        token = secrets.token_urlsafe(32)
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(token + "\n", encoding="utf-8", newline="\n")
        self._harden(self._token_path)
        return token

    def start_session(self, token: str) -> str | None:
        """Consume a bootstrap token or the persistent token; return a session id."""
        supplied = token.strip()
        if not supplied:
            return None
        if self._bootstrap and hmac.compare_digest(supplied, self._bootstrap):
            self._bootstrap = ""
        elif not hmac.compare_digest(supplied, self._token):
            return None
        session = secrets.token_urlsafe(32)
        self._sessions.add(session)
        return session

    def rotate(self) -> str:
        """Replace the persistent bearer token and invalidate sessions and devices."""
        token = secrets.token_urlsafe(32)
        atomic_write(self._token_path, token + "\n")
        with contextlib.suppress(OSError):
            os.chmod(self._token_path, 0o600)
        self._token = token
        self._sessions.clear()
        self._devices.clear()
        self._pairings.clear()
        self._save_devices()
        self._audit("token.rotate")
        return token

    def _load_devices(self) -> list[dict[str, Any]]:
        try:
            payload = json.loads(self._devices_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        devices = payload.get("devices") if isinstance(payload, dict) else None
        if not isinstance(devices, list):
            return []
        clean: list[dict[str, Any]] = []
        for item in devices:
            if not isinstance(item, dict):
                continue
            if not all(key in item for key in ("id", "label", "token_sha256")):
                continue
            clean.append(
                {
                    "id": str(item["id"]),
                    "label": str(item["label"]),
                    "token_sha256": str(item["token_sha256"]),
                    "created_at": float(item.get("created_at") or 0),
                    "last_seen": float(item.get("last_seen") or 0),
                    "expires_at": float(
                        item.get("expires_at") or (float(item.get("created_at") or 0) + DEVICE_TTL)
                    ),
                }
            )
        return clean

    def _save_devices(self) -> None:
        atomic_write(
            self._devices_path,
            json.dumps({"devices": self._devices}, ensure_ascii=False, indent=2) + "\n",
        )
        self._harden(self._devices_path)

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def pairing_start(self, label: str = "device", *, ttl: float = PAIRING_TTL) -> dict[str, Any]:
        now = time.time()
        self._pairings = {
            code: item for code, item in self._pairings.items() if item["expires"] > now
        }
        code = secrets.token_urlsafe(9)
        clean_label = (label or "device").strip()[:80] or "device"
        self._pairings[code] = {"label": clean_label, "expires": now + ttl}
        self._audit("pair.start", label=clean_label)
        return {"code": code, "label": clean_label, "expires_in": int(ttl)}

    def pair(self, code: str, label: str | None = None) -> dict[str, Any] | None:
        item = self._pairings.pop(code.strip(), None)
        if item is None or item["expires"] <= time.time():
            self._audit("pair.failure", reason="invalid_or_expired")
            return None
        now = time.time()
        token = DEVICE_PREFIX + secrets.token_urlsafe(32)
        device = {
            "id": f"dev-{secrets.token_hex(6)}",
            "label": ((label or item["label"]) or "device").strip()[:80] or "device",
            "token_sha256": self._digest(token),
            "created_at": now,
            "last_seen": now,
            "expires_at": now + DEVICE_TTL,
        }
        self._devices.append(device)
        self._save_devices()
        self._audit("pair.success", device_id=device["id"], label=device["label"])
        return {
            "device_id": device["id"],
            "label": device["label"],
            "token": token,
            "expires_at": device["expires_at"],
        }

    def devices(self) -> list[dict[str, Any]]:
        return [
            {
                "id": item["id"],
                "label": item["label"],
                "created_at": item["created_at"],
                "last_seen": item["last_seen"],
                "expires_at": item.get("expires_at", 0),
            }
            for item in self._devices
        ]

    def revoke_device(self, device_id: str) -> bool:
        remaining = [item for item in self._devices if item["id"] != device_id]
        if len(remaining) == len(self._devices):
            return False
        self._devices = remaining
        self._save_devices()
        self._audit("device.revoke", device_id=device_id)
        return True

    def _device(self, token: str) -> dict[str, Any] | None:
        digest = self._digest(token)
        for item in self._devices:
            if hmac.compare_digest(item["token_sha256"], digest):
                now = time.time()
                expires = item.get("expires_at")
                if expires is None:
                    expires = float(item["created_at"]) + DEVICE_TTL
                if float(expires) <= now:
                    return None
                if now - float(item["last_seen"]) > 60:
                    item["last_seen"] = now
                    self._save_devices()
                return item
        return None

    def is_authenticated(self, request: Request) -> bool:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            supplied = header[7:].strip()
            if supplied and hmac.compare_digest(supplied, self._token):
                return True
            if supplied and self._device(supplied) is not None:
                return True
        cookie = request.cookies.get(COOKIE_NAME)
        return bool(cookie and cookie in self._sessions)


def require_write(request: Request) -> None:
    state = request.app.state.works
    if not state.writable:
        raise ReadOnlyError("the daemon is read-only; start it with --write")
    if not state.security.is_authenticated(request):
        raise AuthError("a write token is required; open the daemon with its bootstrap URL")
