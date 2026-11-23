from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from tests.test_confirm import _delivered
from works.application.delivery.confirm import confirm
from works.application.execution.preview import (
    PlaywrightPreview,
    PreviewResult,
    PreviewScript,
    PreviewStep,
)
from works.domain.errors import ConfigError
from works.interfaces.cli.main import main


class FakePage:
    def __init__(self, *, fail_on: str | None = None) -> None:
        self.calls: list[tuple] = []
        self.fail_on = fail_on

    def goto(self, url: str, **kwargs) -> None:
        if self.fail_on == "goto":
            raise RuntimeError("navigation failed")
        self.calls.append(("goto", url))

    def click(self, selector: str, **kwargs) -> None:
        self.calls.append(("click", selector))

    def fill(self, selector: str, value: str, **kwargs) -> None:
        self.calls.append(("fill", selector, value))

    def wait_for_selector(self, selector: str, **kwargs) -> None:
        self.calls.append(("visible", selector))

    def locator(self, selector: str):
        self.calls.append(("locator", selector))
        return FakeLocator()

    def get_by_text(self, value: str):
        self.calls.append(("text", value))
        return FakeText()

    def wait_for_timeout(self, timeout: int) -> None:
        self.calls.append(("wait", timeout))

    def screenshot(self, *, path: str) -> None:
        self.calls.append(("screenshot", path))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"png")

    def close(self) -> None:
        self.calls.append(("close",))


class FakeLocator:
    def inner_text(self, **kwargs) -> str:
        return "ready"


class FakeText:
    def __init__(self) -> None:
        self.first = self

    def wait_for(self, **kwargs) -> None:
        return None


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.closed = False

    def new_page(self) -> FakePage:
        return self.page

    def close(self) -> None:
        self.closed = True
        self.page.close()


class FakeChromium:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    def launch(self, **kwargs) -> FakeBrowser:
        return FakeBrowser(self.page)


class FakePlaywright:
    def __init__(self, page: FakePage) -> None:
        self.chromium = FakeChromium(page)


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.closed = False

    def __enter__(self) -> FakePlaywright:
        return FakePlaywright(self.page)

    def __exit__(self, *args) -> bool:
        self.closed = True
        return False


def _install_fake_playwright(monkeypatch, page: FakePage) -> FakeContext:
    import types

    sync_api = types.ModuleType("playwright.sync_api")
    context = FakeContext(page)
    sync_api.sync_playwright = lambda: context  # type: ignore[attr-defined]
    package = types.ModuleType("playwright")
    package.sync_api = sync_api  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    return context


def _all_actions() -> PreviewScript:
    return PreviewScript(
        start_url="http://app.test",
        steps=[
            PreviewStep(action="goto", url="http://app.test/login"),
            PreviewStep(action="expect_visible", selector="#login"),
            PreviewStep(action="fill", selector="#login", value="demo"),
            PreviewStep(action="click", selector="#submit"),
            PreviewStep(action="expect_text", selector=".status", value="ready"),
            PreviewStep(action="wait", timeout_ms=1),
            PreviewStep(action="screenshot"),
        ],
    )


class FakePreview:
    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok
        self.seen: PreviewScript | None = None

    def run(self, script: PreviewScript, run_dir: Path) -> PreviewResult:
        self.seen = script
        return PreviewResult(
            ok=self.ok,
            target=f"preview {script.start_url}",
            steps=len(script.steps) + 1,
            screenshots=[str(run_dir / "preview" / "01-final.png")],
            notes=["preview: ok" if self.ok else "preview: failed"],
            exit_code=0 if self.ok else 1,
        )


def _script() -> PreviewScript:
    return PreviewScript(
        start_url="http://app.test/login",
        steps=[
            PreviewStep(action="expect_visible", selector="#login"),
            PreviewStep(action="fill", selector="#login", value="demo"),
            PreviewStep(action="click", selector="#submit"),
            PreviewStep(action="expect_text", selector=".status", value="ready"),
        ],
    )


def test_preview_script_validates_steps(tmp_path) -> None:
    path = tmp_path / "preview.yaml"
    path.write_text(
        "schema_version: 1\n"
        "start_url: http://app.test\n"
        "steps:\n"
        "  - action: expect_visible\n"
        "    selector: '#done'\n",
        encoding="utf-8",
    )

    script = PreviewScript.from_path(path)

    assert script.start_url == "http://app.test"
    assert script.steps[0].selector == "#done"


def test_preview_script_rejects_a_missing_selector(tmp_path) -> None:
    path = tmp_path / "preview.yaml"
    path.write_text(
        "start_url: http://app.test\nsteps:\n  - action: click\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="needs a selector"):
        PreviewScript.from_path(path)


def test_playwright_fails_closed_when_the_extra_is_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setitem(sys.modules, "playwright", None)

    with pytest.raises(ConfigError, match="Playwright extra"):
        PlaywrightPreview().run(_script(), tmp_path)


def test_playwright_drives_every_step_and_closes(monkeypatch, tmp_path) -> None:
    page = FakePage()
    context = _install_fake_playwright(monkeypatch, page)

    result = PlaywrightPreview().run(_all_actions(), tmp_path)

    assert result.ok is True
    assert result.steps == 8
    assert ("goto", "http://app.test/login") in page.calls
    assert ("click", "#submit") in page.calls
    assert ("fill", "#login", "demo") in page.calls
    assert ("visible", "#login") in page.calls
    assert ("locator", ".status") in page.calls
    assert ("wait", 1) in page.calls
    assert context.closed is True
    assert len(result.screenshots) == 8
    assert all(Path(item).exists() for item in result.screenshots)


def test_playwright_records_a_failed_navigation(monkeypatch, tmp_path) -> None:
    page = FakePage(fail_on="goto")
    _install_fake_playwright(monkeypatch, page)
    script = PreviewScript(
        start_url="http://app.test",
        steps=[PreviewStep(action="expect_visible", selector="#login")],
    )

    result = PlaywrightPreview().run(script, tmp_path)

    assert result.ok is False
    assert result.exit_code == 1
    assert "preview failed" in result.notes[0]


def test_confirm_uses_the_preview_runner(paths, repo, tmp_path) -> None:
    task, _delivery, _ = _delivered(paths, repo, tmp_path)
    runner = FakePreview()

    result = confirm(paths, task.id, preview=_script(), preview_runner=runner)

    assert result.ok is True
    assert result.target == "preview http://app.test/login"
    assert result.screenshots == [str(paths.runs / "r-deliver" / "preview" / "01-final.png")]
    assert runner.seen is not None
    body = json.loads((paths.runs / "r-deliver" / "confirmation.json").read_text(encoding="utf-8"))
    assert body["screenshots"] == result.screenshots


def test_a_failing_preview_is_recorded(paths, repo, tmp_path) -> None:
    task, _delivery, _ = _delivered(paths, repo, tmp_path)

    result = confirm(paths, task.id, preview=_script(), preview_runner=FakePreview(ok=False))

    assert result.ok is False
    assert result.exit_code == 1
    assert "preview: failed" in result.notes


def test_the_cli_confirm_preview_uses_the_driver(monkeypatch, paths, repo, tmp_path) -> None:
    task, _delivery, _ = _delivered(paths, repo, tmp_path)
    script = tmp_path / "preview.yaml"
    script.write_text(
        "start_url: http://app.test\nsteps:\n  - action: expect_visible\n    selector: '#done'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "works.application.delivery.confirm.PlaywrightPreview", lambda: FakePreview()
    )
    out, err = io.StringIO(), io.StringIO()

    with redirect_stdout(out), redirect_stderr(err):
        code = main(
            ["--home", str(paths.root), "confirm", task.id, "--preview", str(script), "--json"]
        )

    assert code == 0, err.getvalue()
    body = json.loads(out.getvalue().strip().splitlines()[-1])
    assert body["ok"] is True
    assert body["target"] == "preview http://app.test"
