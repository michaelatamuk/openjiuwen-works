"""Prompts are versioned files, rendered safely, never assembled from free text."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from string import Template

from .errors import ConfigError

DEFAULT_PROMPT = Path("flows/fix-issue/prompts/build.md")
REQUIRED = ("worktree", "ref", "title")


@dataclass(frozen=True)
class Prompt:
    name: str
    path: Path
    text: str
    sha256: str

    def render(self, **values: str) -> str:
        return Template(self.text).safe_substitute(values)


def load_prompt(path: Path, *, name: str = "build") -> Prompt:
    resolved = path.expanduser()
    if not resolved.exists():
        raise ConfigError(f"prompt not found: {resolved}")
    text = resolved.read_text(encoding="utf-8")
    missing = [key for key in REQUIRED if key not in Template(text).get_identifiers()]
    if missing:
        raise ConfigError(f"{resolved} is missing prompt variables: {', '.join(missing)}")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Prompt(name=name, path=resolved, text=text, sha256=digest)
