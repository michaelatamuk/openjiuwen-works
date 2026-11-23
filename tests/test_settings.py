from __future__ import annotations

import json

import pytest

from works.errors import ConfigError
from works.settings import (
    BuilderSettings,
    builder_health,
    credential_status,
    load_builder_settings,
    save_builder_settings,
    settings_path,
)


def test_defaults_are_the_claude_code_provider(paths) -> None:
    settings = load_builder_settings(paths)

    assert settings.provider == "claudecode"
    assert settings.resolved_verifier_provider == "claudecode"


def test_settings_round_trip_and_ignore_unknown_keys(paths) -> None:
    saved = save_builder_settings(
        paths,
        {
            "provider": "dsh",
            "verifier_provider": "codex",
            "model": "deepseek-chat",
            "verifier_model": "gpt-5",
        },
    )

    assert settings_path(paths).exists()
    assert load_builder_settings(paths) == saved
    assert saved.resolved_verifier_provider == "codex"


def test_an_invalid_provider_is_refused(paths) -> None:
    with pytest.raises(ConfigError, match="unknown harness provider"):
        save_builder_settings(paths, {"provider": "not-a-provider"})


def test_an_invalid_settings_file_is_a_config_error(paths) -> None:
    path = settings_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{", encoding="utf-8")

    with pytest.raises(ConfigError, match="cannot read"):
        load_builder_settings(paths)


def test_credential_labels_are_provider_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKS_MODEL_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("WORKS_VERIFIER_API_KEY", raising=False)
    assert credential_status() == {"builder": "missing", "verifier": "missing"}

    monkeypatch.setenv("ANTHROPIC_API_KEY", "builder")
    assert credential_status() == {"builder": "ready", "verifier": "builder"}

    monkeypatch.setenv("WORKS_VERIFIER_API_KEY", "builder")
    assert credential_status()["verifier"] == "shared"

    monkeypatch.setenv("WORKS_VERIFIER_API_KEY", "verifier")
    assert credential_status()["verifier"] == "separate"


def test_builder_health_exposes_labels_not_secret_names(paths) -> None:
    health = builder_health(paths, BuilderSettings(provider="dsh", verifier_provider="codex"))

    assert health["provider"] == "dsh"
    assert health["verifier_provider"] == "codex"
    assert set(health["providers"]) == {"claudecode", "dsh", "codex"}
    assert "ANTHROPIC_API_KEY" not in json.dumps(health)
    assert "WORKS_VERIFIER_API_KEY" not in json.dumps(health)
