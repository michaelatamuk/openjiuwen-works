"""Local builder settings. Credentials stay in the environment; only choices are stored here."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator

from .config import WorksPaths
from .errors import ConfigError
from .harness.providers import DEFAULT_PROVIDER, availability, validate_provider

SETTINGS_PATH = Path(".works") / "settings.json"


class BuilderSettings(BaseModel):
    provider: str = DEFAULT_PROVIDER
    verifier_provider: str | None = None
    model: str | None = None
    verifier_model: str | None = None

    @field_validator("provider")
    @classmethod
    def _provider(cls, value: str) -> str:
        return validate_provider(value, env_name="settings.json")

    @field_validator("verifier_provider")
    @classmethod
    def _verifier_provider(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        return validate_provider(str(value), env_name="settings.json")

    @field_validator("model", "verifier_model")
    @classmethod
    def _model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @property
    def resolved_verifier_provider(self) -> str:
        return self.verifier_provider or self.provider


def settings_path(paths: WorksPaths) -> Path:
    return paths.root / SETTINGS_PATH


def load_builder_settings(paths: WorksPaths) -> BuilderSettings:
    path = settings_path(paths)
    if not path.exists():
        return BuilderSettings()
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read {SETTINGS_PATH.as_posix()}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{SETTINGS_PATH.as_posix()} must contain a mapping")
    try:
        return BuilderSettings.model_validate(raw)
    except ValueError as exc:
        raise ConfigError(f"{SETTINGS_PATH.as_posix()} is invalid: {exc}") from exc


def save_builder_settings(paths: WorksPaths, payload: dict[str, Any]) -> BuilderSettings:
    try:
        settings = BuilderSettings.model_validate(payload)
    except ValueError as exc:
        raise ConfigError(f"builder settings are invalid: {exc}") from exc
    path = settings_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(settings.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return settings


def _builder_key() -> str:
    return os.environ.get("WORKS_MODEL_KEY") or os.environ.get("ANTHROPIC_API_KEY") or ""


def credential_status() -> dict[str, str]:
    """Provider-neutral labels; never return the secret or the variable name."""
    builder = _builder_key()
    verifier = os.environ.get("WORKS_VERIFIER_API_KEY") or ""
    if not builder:
        return {"builder": "missing", "verifier": "missing"}
    if verifier and verifier != builder:
        return {"builder": "ready", "verifier": "separate"}
    if verifier:
        return {"builder": "ready", "verifier": "shared"}
    return {"builder": "ready", "verifier": "builder"}


def builder_health(paths: WorksPaths, settings: BuilderSettings | None = None) -> dict[str, Any]:
    current = settings or BuilderSettings()
    return {
        "provider": current.provider,
        "verifier_provider": current.resolved_verifier_provider,
        "model": current.model,
        "verifier_model": current.verifier_model,
        "providers": {
            "claudecode": {
                "available": availability().get("claudecode", False),
                "label": "Claude Code",
                "kind": "General coding harness",
            },
            "dsh": {
                "available": availability().get("dsh", False),
                "label": "DeepSeek Harness",
                "kind": "DeepSeek native",
            },
            "codex": {
                "available": availability().get("codex", False),
                "label": "Codex",
                "kind": "OpenAI Codex",
            },
        },
        "credentials": credential_status(),
    }
