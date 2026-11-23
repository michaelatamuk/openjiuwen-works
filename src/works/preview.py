"""Browser preview: drive one real user path and attach the artifacts to the confirmation.

The driver is optional. Works never pretends a GUI change is confirmed from a unit test alone; a
product that needs a browser must provide a preview script and the optional Playwright extra
(`uv sync --extra preview`, then `playwright install chromium`). Without it the command fails
closed with a configuration error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from .errors import ConfigError

Action = Literal[
    "goto",
    "click",
    "fill",
    "expect_text",
    "expect_visible",
    "wait",
    "screenshot",
]


class PreviewStep(BaseModel):
    action: Action
    url: str = ""
    selector: str = ""
    value: str = ""
    timeout_ms: int = Field(default=5000, gt=0)

    @model_validator(mode="after")
    def _check(self) -> PreviewStep:
        needs_url = self.action == "goto"
        needs_selector = self.action in ("click", "fill", "expect_visible")
        if needs_url and not self.url:
            raise ValueError("a goto step needs a url")
        if needs_selector and not self.selector:
            raise ValueError(f"a {self.action} step needs a selector")
        if self.action == "fill" and not self.value:
            raise ValueError("a fill step needs a value")
        if self.action == "expect_text" and not (self.selector or self.value):
            raise ValueError("an expect_text step needs a selector or a value")
        return self


class PreviewScript(BaseModel):
    schema_version: int = 1
    start_url: str = Field(min_length=1)
    artifact_dir: str = "preview"
    steps: list[PreviewStep] = Field(min_length=1)

    @classmethod
    def from_path(cls, path: Path) -> PreviewScript:
        if not path.exists():
            raise ConfigError(f"preview script not found: {path}")
        try:
            raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError(f"{path} must contain a mapping")
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise ConfigError(f"{path} is not a valid preview script:\n{exc}") from exc


class PreviewResult(BaseModel):
    ok: bool
    target: str
    steps: int = 0
    screenshots: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    exit_code: int = 0
    output_tail: str = ""


class Preview(Protocol):
    def run(self, script: PreviewScript, run_dir: Path) -> PreviewResult: ...


class PlaywrightPreview:
    """A real Chromium run. Imported lazily so the base install has no browser dependency."""

    def run(self, script: PreviewScript, run_dir: Path) -> PreviewResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ConfigError(
                "browser preview needs the optional Playwright extra: "
                "`uv sync --extra preview` and `playwright install chromium`"
            ) from exc

        artifact_dir = run_dir / script.artifact_dir
        artifact_dir.mkdir(parents=True, exist_ok=True)
        screenshots: list[str] = []
        notes: list[str] = []
        steps = 0
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(script.start_url, wait_until="load", timeout=30000)
                steps = 1
                for index, step in enumerate(script.steps, start=1):
                    self._step(page, step, artifact_dir, index, screenshots)
                    steps += 1
                    notes.append(f"{step.action}: ok")
                page.screenshot(path=str(artifact_dir / f"{len(script.steps) + 1:02d}-final.png"))
                screenshots.append(str(artifact_dir / f"{len(script.steps) + 1:02d}-final.png"))
                browser.close()
            return PreviewResult(
                ok=True,
                target=f"preview {script.start_url}",
                steps=steps,
                screenshots=screenshots,
                notes=notes,
            )
        except ConfigError:
            raise
        except Exception as exc:  # playwright raises a wide family of errors
            notes.append(f"preview failed: {exc}")
            return PreviewResult(
                ok=False,
                target=f"preview {script.start_url}",
                steps=steps,
                screenshots=screenshots,
                notes=notes,
                exit_code=1,
                output_tail=str(exc)[-4000:],
            )

    def _step(
        self,
        page: Any,
        step: PreviewStep,
        artifact_dir: Path,
        index: int,
        screenshots: list[str],
    ) -> None:
        if step.action == "goto":
            page.goto(step.url, wait_until="load", timeout=step.timeout_ms)
        elif step.action == "click":
            page.click(step.selector, timeout=step.timeout_ms)
        elif step.action == "fill":
            page.fill(step.selector, step.value, timeout=step.timeout_ms)
        elif step.action == "expect_visible":
            page.wait_for_selector(step.selector, state="visible", timeout=step.timeout_ms)
        elif step.action == "expect_text":
            if step.selector:
                text = page.locator(step.selector).inner_text(timeout=step.timeout_ms)
                if step.value and step.value not in text:
                    raise AssertionError(f"{step.selector} does not contain {step.value!r}")
            elif step.value:
                page.get_by_text(step.value).first.wait_for(timeout=step.timeout_ms)
        elif step.action == "wait":
            page.wait_for_timeout(step.timeout_ms)
        if step.action != "screenshot":
            path = artifact_dir / f"{index:02d}-{step.action}.png"
            page.screenshot(path=str(path))
            screenshots.append(str(path))
        else:
            path = artifact_dir / f"{index:02d}-screenshot.png"
            page.screenshot(path=str(path))
            screenshots.append(str(path))
