from __future__ import annotations

import json

from tests.unit.domain.test_evidence import fixed_evidence
from works.application.proof.verify import verify_run
from works.config.paths import WorksPaths
from works.domain.evidence import Evidence, write_evidence
from works.domain.evidence.summary import render_summary, summary_digest
from works.domain.records import Priority, ScenarioOutcome
from works.domain.risk import RiskLevel, RiskRating


def test_the_summary_has_the_five_sections() -> None:
    page = render_summary(fixed_evidence())
    for heading in (
        "## What was wrong",
        "## What caused it",
        "## What changed",
        "## What proves it",
        "## What was not tested",
    ):
        assert heading in page


def test_the_summary_is_deterministic() -> None:
    evidence = fixed_evidence()
    assert render_summary(evidence) == render_summary(evidence)
    assert summary_digest(render_summary(evidence)) == summary_digest(render_summary(evidence))


def test_a_missing_field_is_named_instead_of_invented() -> None:
    evidence = fixed_evidence().model_copy(
        update={
            "task_title": "",
            "plan_summary": None,
            "findings": [],
            "reproduction_command": [],
            "diff_stat": [],
            "files_changed": [],
            "verdict": None,
            "challenge": None,
            "risk": None,
            "diff_sha256": "",
            "proof_sha256": "",
            "not_tested": [],
        }
    )
    page = render_summary(evidence)
    assert "The task title was not recorded." in page
    assert "The reproduction command was not recorded." in page
    assert "The cause was not recorded in the plan or the findings." in page
    assert "No file change was recorded." in page
    assert "The verdict was not recorded." in page
    assert "Nothing was declared untested." in page


def test_numbers_come_from_the_record_only() -> None:
    evidence = fixed_evidence().model_copy(
        update={
            "task_title": "parser drops the last line",
            "risk": RiskRating(
                level=RiskLevel.HIGH,
                reasons=["security-sensitive path: payments/charge.py"],
                files=2,
                lines=41,
            ),
            "not_tested": ["the Windows runner"],
        }
    )
    page = render_summary(evidence)
    assert "parser drops the last line." in page
    assert "1 file(s), 2 line(s) changed." in page
    assert "Risk: high — security-sensitive path: payments/charge.py." in page
    assert "- the Windows runner" in page


def test_the_verdict_counts_come_from_the_outcomes() -> None:
    base = fixed_evidence()
    outcomes = [
        ScenarioOutcome(
            id="must",
            priority=Priority.P0,
            weight=1.0,
            passed=False,
            exit_code=1,
            duration_ms=10,
            output_sha256="a" * 64,
        ),
        ScenarioOutcome(
            id="nice",
            priority=Priority.P1,
            weight=1.0,
            passed=True,
            exit_code=0,
            duration_ms=10,
            output_sha256="b" * 64,
        ),
    ]
    verdict = base.verdict.model_copy(update={"outcomes": outcomes, "allow": False})
    page = render_summary(base.model_copy(update={"verdict": verdict}))
    assert "Must-pass checks: 0 of 1 passed." in page
    assert "Supporting checks: 1 of 1 passed." in page


def test_an_old_record_keeps_its_proof_hash() -> None:
    evidence = fixed_evidence()
    original = evidence.bind().proof_sha256
    raw = json.loads(evidence.model_dump_json())
    raw.pop("task_title")
    raw.pop("summary")
    old = Evidence.model_validate(raw)
    assert old.bind().proof_sha256 == original


def test_write_evidence_binds_the_summary_and_its_artifact(tmp_path) -> None:
    json_path, _ = write_evidence(tmp_path, fixed_evidence())
    stored = Evidence.model_validate_json(json_path.read_text(encoding="utf-8"))
    assert stored.summary.startswith("## What was wrong")
    artifact = next(item for item in stored.artifacts if item.kind == "summary")
    assert (tmp_path / artifact.path).read_text(encoding="utf-8") == stored.summary
    assert artifact.sha256 == summary_digest(stored.summary)
    assert stored.bind().proof_sha256 == stored.proof_sha256


def test_a_bound_record_without_a_summary_is_not_rewritten(tmp_path) -> None:
    bound = fixed_evidence().bind()
    json_path, _ = write_evidence(tmp_path, bound)
    stored = Evidence.model_validate_json(json_path.read_text(encoding="utf-8"))
    assert stored.summary == ""
    assert stored.proof_sha256 == bound.proof_sha256
    assert not (tmp_path / "artifacts" / "summary.md").exists()


def test_a_summary_run_verifies_end_to_end(tmp_path) -> None:
    paths = WorksPaths(tmp_path / "works")
    run_id = "r-summary-verify"
    run_dir = paths.runs / run_id
    run_dir.mkdir(parents=True)
    write_evidence(run_dir, fixed_evidence().model_copy(update={"run_id": run_id}))
    result = verify_run(paths, run_id)
    assert result.ok, [check for check in result.checks if not check.ok]
