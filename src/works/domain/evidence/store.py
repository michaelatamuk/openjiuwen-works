"""Writing the bound evidence record and its markdown rendering."""

from __future__ import annotations

from pathlib import Path

from works.domain.evidence.models import Evidence
from works.domain.evidence.render import render_markdown


def write_evidence(directory: Path, evidence: Evidence) -> tuple[Path, Path]:
    bound = evidence.bind() if not evidence.proof_sha256 else evidence
    json_path = directory / "evidence.json"
    md_path = directory / "evidence.md"
    json_path.write_text(bound.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    md_path.write_text(render_markdown(bound), encoding="utf-8", newline="\n")
    return json_path, md_path
