from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from works.cli import main
from works.errors import PolicyError
from works.readiness import assess, ensure_ready


def _repo(tmp_path: Path, *, command: str | None = None, allow: list[str] | None = None) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "demo.yaml").write_text(
        """
schema_version: 1
product: demo
features:
  - id: demo
    name: Demo
    user_path: A person uses the product
    expected: It works
    command: "true"
""",
        encoding="utf-8",
    )
    (tmp_path / ".works").mkdir()
    ok = command or '{python} -c "raise SystemExit(0)"'
    allowed = allow or []
    spec = [
        "schema_version: 1",
        "features: features",
        "commands:",
        f"  lint: {json.dumps(ok)}",
        f"  format: {json.dumps(ok)}",
        f"  types: {json.dumps(ok)}",
        f"  tests: {json.dumps(ok)}",
        f"  verify: {json.dumps(ok)}",
        f"  architecture: {json.dumps(ok)}",
        "suppressions:",
        "  allow: []" if not allowed else "  allow:",
        *[f"    - {json.dumps(item)}" for item in allowed],
    ]
    (tmp_path / ".works" / "readiness.yaml").write_text("\n".join(spec) + "\n", encoding="utf-8")
    return tmp_path


def test_a_configured_repository_is_green(tmp_path) -> None:
    report = assess(_repo(tmp_path))

    assert report.status == "pass"
    assert report.passed == report.total == 10
    assert all(check.status == "pass" for check in report.checks)


def test_a_failing_command_makes_the_gate_red(tmp_path) -> None:
    report = assess(_repo(tmp_path, command='{python} -c "raise SystemExit(1)"'))

    assert report.status == "fail"
    assert report.failed >= 1


def test_an_unknown_suppression_fails_the_gate(tmp_path) -> None:
    repo = _repo(tmp_path, allow=[])
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("x = 1  # noqa: E501\n", encoding="utf-8")

    report = assess(repo)

    assert report.status == "fail"
    assert report.unknown_suppressions[0].location == "src/a.py:1:noqa"


def test_a_known_suppression_is_allowed(tmp_path) -> None:
    repo = _repo(tmp_path, allow=["src/a.py:1:noqa"])
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("x = 1  # noqa: E501\n", encoding="utf-8")

    report = assess(repo)

    assert report.status == "pass"
    assert not report.unknown_suppressions


def test_the_cli_returns_a_blocked_code_for_a_red_gate(tmp_path) -> None:
    repo = _repo(tmp_path, command='{python} -c "raise SystemExit(1)"')
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(["readiness", "--repo", str(repo), "--json"])

    assert code == 8
    payload = json.loads(out.getvalue())
    assert payload["ok"] is False
    assert payload["status"] == "fail"


def test_ensure_ready_refuses_a_red_repository(tmp_path) -> None:
    repo = _repo(tmp_path, command='{python} -c "raise SystemExit(1)"')

    with pytest.raises(PolicyError, match="readiness is red"):
        ensure_ready(repo)
