from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from works.application.execution.scenarios import judge
from works.domain.evidence import DiffStatRow, Evidence, render_markdown
from works.domain.policy import PolicyReport, Violation
from works.domain.records import (
    Challenge,
    CommandRecord,
    Finding,
    Priority,
    ScenarioOutcome,
    StopReason,
    TaskState,
)


def command(step: str, exit_code: int, digest: str) -> CommandRecord:
    return CommandRecord(
        step=step,
        argv=["python", "-m", "pytest", "-q"],
        cwd="/tmp/repo",  # noqa: S108 - a fixed string keeps the golden page stable
        exit_code=exit_code,
        duration_ms=180 if step == "reproduce" else 240,
        output_sha256=digest * 64,
        stdout_tail="",
        stderr_tail="",
    )


def fixed_evidence() -> Evidence:
    verdict = judge(
        [
            ScenarioOutcome(
                id="add-negative",
                priority=Priority.P0,
                weight=1.0,
                passed=True,
                exit_code=0,
                duration_ms=90,
                output_sha256="b" * 64,
            ),
            ScenarioOutcome(
                id="add-positive",
                priority=Priority.P0,
                weight=1.0,
                passed=True,
                exit_code=0,
                duration_ms=80,
                output_sha256="c" * 64,
            ),
            ScenarioOutcome(
                id="mul-positive",
                priority=Priority.P1,
                weight=1.0,
                passed=True,
                exit_code=0,
                duration_ms=70,
                output_sha256="d" * 64,
            ),
        ],
        run_id="r-20260101T000000-abcdef",
    )
    return Evidence(
        run_id="r-20260101T000000-abcdef",
        task_id="t-0123456789ab",
        flow="fix-issue",
        product="openjiuwen",
        source="manual:GH-1",
        base_commit="abc1234",
        state=TaskState.PROVED,
        stop_reason=StopReason.COMPLETED,
        model="fake-builder-1",
        provider="fixture",
        prompt_name="build",
        prompt_sha256="f" * 64,
        harness="native",
        tokens=1200,
        usd=0.012,
        duration_ms=4321,
        files_changed=["calc/core.py"],
        diff_stat=[DiffStatRow(path="calc/core.py", added=1, removed=1)],
        policy=PolicyReport(ok=True),
        reproduce=command("reproduce", 1, "a"),
        test=command("test", 0, "e"),
        verdict=verdict,
        findings=[
            Finding(
                step="build",
                summary="add subtracted instead of adding",
                confidence=0.95,
                uncertainty="none observed",
                evidence=["calc/core.py:5"],
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ],
        challenge=Challenge(
            allow=True,
            reason="the change is the smallest one that explains the defect",
            concerns=["no stress test for integer overflow"],
            model="fake-challenger-1",
            provider="fixture",
            prompt_sha256="e" * 64,
        ),
        not_tested=["Windows-specific path handling"],
        diff=(
            "diff --git a/calc/core.py b/calc/core.py\n"
            "--- a/calc/core.py\n"
            "+++ b/calc/core.py\n"
            "@@ -4,2 +4,2 @@\n"
            " def add(a: int, b: int) -> int:\n"
            "-    return a - b\n"
            "+    return a + b\n"
        ),
    )


def test_proof_is_bound_to_its_content() -> None:
    bound = fixed_evidence().bind()
    assert len(bound.proof_sha256) == 64
    assert len(bound.diff_sha256) == 64
    assert bound.bind() == bound
    changed = bound.model_copy(update={"diff": bound.diff + "x"}).bind()
    assert changed.proof_sha256 != bound.proof_sha256


def test_a_blocked_proof_says_block() -> None:
    evidence = fixed_evidence().bind()
    blocked_verdict = judge(
        [
            ScenarioOutcome(
                id="add-negative",
                priority=Priority.P0,
                weight=1.0,
                passed=False,
                exit_code=1,
                duration_ms=90,
                output_sha256="b" * 64,
            )
        ],
        run_id=evidence.run_id,
    )
    blocked = evidence.model_copy(
        update={
            "state": TaskState.BLOCKED,
            "stop_reason": StopReason.POLICY_VIOLATION,
            "verdict": blocked_verdict,
            "policy": PolicyReport(
                ok=False,
                violations=[Violation(path="tests/test_core.py", reason="denied by policy")],
            ),
        }
    ).bind()
    page = render_markdown(blocked)
    assert "BLOCK" in page
    assert "tests/test_core.py" in page
    assert "policy_violation" in page


def test_no_change_is_stated_not_implied() -> None:
    evidence = fixed_evidence().model_copy(
        update={"diff": "", "files_changed": [], "diff_stat": []}
    )
    page = render_markdown(evidence)
    assert "No change was produced." in page


def test_cost_and_provider_split_are_rendered_when_recorded() -> None:
    evidence = fixed_evidence().model_copy(
        update={
            "builder_tokens": 900,
            "verifier_tokens": 300,
            "builder_usd": 0.009,
            "verifier_usd": 0.003,
            "verification_share": 0.25,
            "verifier_model": "verifier-1",
            "verifier_provider": "anthropic",
            "provider_split": True,
            "credential_split": True,
        }
    )

    page = render_markdown(evidence.bind())

    assert "builder tokens: `900`" in page
    assert "verifier tokens: `300`" in page
    assert "verification share: `25.0%`" in page
    assert "provider split: `yes`" in page
    assert "credential split: `yes`" in page


def test_the_page_answers_the_four_questions() -> None:
    page = render_markdown(fixed_evidence().bind())
    for heading in (
        "## Verdict",
        "## Findings",
        "## Commands",
        "## Change",
        "## Policy",
        "## Residual risk",
        "## Cost",
    ):
        assert heading in page
    assert "Not tested" in page
    assert "add subtracted instead of adding" in page
    assert "sha256" in page


def test_golden_page(factory_root: Path) -> None:
    evidence = fixed_evidence().bind()
    rendered = render_markdown(evidence)
    golden = Path(__file__).resolve().parents[2] / "golden" / "evidence.md"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(rendered, encoding="utf-8", newline="\n")
    assert golden.exists(), "run with UPDATE_GOLDEN=1 once to record the page"
    assert rendered == golden.read_text(encoding="utf-8")


def test_the_page_records_both_prompt_hashes() -> None:
    page = render_markdown(fixed_evidence())
    assert "engine: `native`" in page
    assert "prompt: `build`" in page
    assert "f" * 64 in page
    assert "e" * 64 in page


def test_model_calls_are_part_of_the_proof() -> None:
    from works.domain.evidence.models import ModelCall

    base = fixed_evidence()
    without = base.bind()
    with_calls = base.model_copy(
        update={
            "model_calls": [
                ModelCall(
                    stage="build",
                    provider="deepseek",
                    model="deepseek-chat",
                    version="1.2.3",
                    tokens=1200,
                    usd=0.0042,
                )
            ]
        }
    ).bind()

    assert with_calls.proof_sha256 != without.proof_sha256
    page = render_markdown(with_calls)
    assert "| build | `deepseek` | `deepseek-chat` | `1.2.3` | 1200 | 0.0042 |" in page
