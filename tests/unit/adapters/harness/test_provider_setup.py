from __future__ import annotations

from works.adapters.harness.openjiuwen import provider_setup as ps


def test_missing_providers_point_at_project_extras(monkeypatch) -> None:
    monkeypatch.setattr(ps, "has", lambda module: False)

    setup = ps.provider_setup()

    assert not any(item["available"] for item in setup.values())
    assert setup["native"]["install"] == [ps.NATIVE_EXTRA]
    assert setup["dsh"]["install"][0] == ps.DSH_EXTRA
    assert setup["codex"]["install"] == [ps.CODEX_EXTRA]
    assert setup["claudecode"]["install"] == [ps.CLAUDE_EXTRA]
    assert all("pip install" in hint for hint in setup["native"]["install"])


def test_a_dsh_without_a_home_asks_for_the_home(monkeypatch) -> None:
    monkeypatch.setattr(ps, "has", lambda module: module == "deepseek_harness")
    monkeypatch.delenv("WORKS_DSH_HOME", raising=False)

    item = ps.provider_setup()["dsh"]

    assert item["available"] is False
    assert any("WORKS_DSH_HOME" in hint for hint in item["install"])


def test_an_installed_sdk_with_a_home_is_available(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(ps, "has", lambda module: module == "deepseek_harness")
    monkeypatch.setenv("WORKS_DSH_HOME", str(tmp_path))

    item = ps.provider_setup()["dsh"]

    assert item["available"] is True
    assert item["install"] == []
