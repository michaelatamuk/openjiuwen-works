from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from tests.unit.domain.test_evidence import fixed_evidence
from works.application.proof import verify
from works.application.proof.chain import event_root
from works.application.proof.redact import redact
from works.domain.event import Event
from works.domain.evidence import Artifact


def _write(paths, evidence, run_id: str = "r-proof") -> None:
    run_dir = paths.run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "evidence.json").write_text(evidence.model_dump_json(indent=2), encoding="utf-8")


def test_event_root_changes_when_an_event_is_removed() -> None:
    events = [
        Event(seq=1, ts=datetime.now(tz=UTC), type="task.created", data={"a": 1}),
        Event(seq=2, ts=datetime.now(tz=UTC), type="build.started", data={"attempt": 1}),
    ]
    before = event_root(events)

    assert event_root(events[:1]) != before
    events[1] = events[1].model_copy(update={"data": {"attempt": 2}})
    assert event_root(events) != before


def test_credentials_are_redacted() -> None:
    clean, count = redact("token=ghp_abcdefghijklmnopqrstuvwxyz and sk-abcdefghijklmnop")

    assert "ghp_" not in clean
    assert "sk-" not in clean
    assert clean.count("[redacted]") == count == 2


def test_verify_accepts_a_bound_page(paths) -> None:
    evidence = fixed_evidence().model_copy(update={"task_id": "t-proof"}).bind()
    _write(paths, evidence)

    result = verify.verify_run(paths, "r-proof")

    assert result.ok is True, [check.model_dump() for check in result.checks]


def test_verify_rejects_a_tampered_diff(paths) -> None:
    evidence = fixed_evidence().model_copy(update={"task_id": "t-proof"}).bind()
    tampered = evidence.model_copy(update={"diff": evidence.diff + "\n+ hidden change"})
    _write(paths, tampered)

    result = verify.verify_run(paths, "r-proof")

    assert result.ok is False
    assert any(check.name == "diff" and not check.ok for check in result.checks)


def test_verify_rejects_a_changed_artifact(paths) -> None:
    run_dir = paths.run_dir("r-proof")
    (run_dir / "artifacts").mkdir(parents=True)
    payload = b"log"
    (run_dir / "artifacts" / "x.log").write_bytes(payload)
    evidence = (
        fixed_evidence()
        .model_copy(
            update={
                "task_id": "t-proof",
                "artifacts": [
                    Artifact(
                        kind="log",
                        path="artifacts/x.log",
                        sha256=hashlib.sha256(payload).hexdigest(),
                    )
                ],
            }
        )
        .bind()
    )
    _write(paths, evidence)
    (run_dir / "artifacts" / "x.log").write_bytes(b"different")

    result = verify.verify_run(paths, "r-proof")

    assert result.ok is False


def test_compare_reports_the_verdict_and_cost(paths) -> None:
    first = fixed_evidence().model_copy(update={"task_id": "t-1"}).bind()
    second = fixed_evidence().model_copy(update={"task_id": "t-2", "tokens": 99, "usd": 0.5}).bind()
    _write(paths, first, "r-a")
    _write(paths, second, "r-b")

    data = verify.compare(paths, "r-a", "r-b")

    assert data["tokens"] == [first.tokens, 99]
    assert data["proof_changed"] is True


def test_export_writes_a_tarball(paths, tmp_path: Path) -> None:
    evidence = fixed_evidence().model_copy(update={"task_id": "t-proof"}).bind()
    _write(paths, evidence)
    target = tmp_path / "proof.tar.gz"

    exported = verify.export(paths, "r-proof", target)

    assert exported.exists() and exported.stat().st_size > 0
    manifest = json.loads((paths.run_dir("r-proof") / "manifest.json").read_text("utf-8"))
    assert "evidence.json" in manifest["files"]


def test_a_binary_or_renamed_file_is_visible_and_a_long_diff_is_disclosed() -> None:
    from works.domain.evidence import MAX_DIFF_CHARS, render_markdown

    diff = "Binary files a/logo.png and b/logo.png differ\n" + "x" * (MAX_DIFF_CHARS + 10)
    evidence = fixed_evidence().model_copy(update={"diff": diff})

    page = render_markdown(evidence)

    assert "Binary files" in page
    assert "Diff truncated" in page


def test_an_older_page_without_the_new_fields_still_loads() -> None:
    from works.domain.evidence import Evidence

    payload = {
        "schema_version": 1,
        "run_id": "r-old",
        "task_id": "t-old",
        "flow": "fix-issue",
        "product": "Fixture",
        "source": "manual:OLD-1",
        "state": "proved",
        "stop_reason": "completed",
    }

    evidence = Evidence.model_validate_json(json.dumps(payload))

    assert evidence.event_root is None
    assert evidence.skipped_checks == []
    assert evidence.runtime == {}
