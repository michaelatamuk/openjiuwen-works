"""Writing the bound evidence record and its markdown rendering."""

from __future__ import annotations

from pathlib import Path

from works.domain.evidence.models import Artifact, Evidence
from works.domain.evidence.render import render_markdown
from works.domain.evidence.summary import render_summary, summary_digest

SUMMARY_PATH = "artifacts/summary.md"


def _with_summary(evidence: Evidence) -> Evidence:
    """Attach the deterministic summary before the record is bound."""
    text = render_summary(evidence)
    digest = summary_digest(text)
    artifacts = [artifact for artifact in evidence.artifacts if artifact.path != SUMMARY_PATH]
    artifacts.append(
        Artifact(
            kind="summary",
            path=SUMMARY_PATH,
            sha256=digest,
            description="Plain-language summary of this proof",
        )
    )
    return evidence.model_copy(update={"summary": text, "artifacts": artifacts})


def write_evidence(directory: Path, evidence: Evidence) -> tuple[Path, Path]:
    if not evidence.proof_sha256:
        evidence = _with_summary(evidence)
    bound = evidence.bind() if not evidence.proof_sha256 else evidence
    json_path = directory / "evidence.json"
    md_path = directory / "evidence.md"
    json_path.write_text(bound.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    md_path.write_text(render_markdown(bound), encoding="utf-8", newline="\n")
    if bound.summary:
        summary_path = directory / SUMMARY_PATH
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(bound.summary, encoding="utf-8", newline="\n")
    return json_path, md_path
