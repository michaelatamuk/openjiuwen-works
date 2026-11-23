from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from works.adapters.queue.store import Queue
from works.application.intake.sources import Issue
from works.interfaces.cli.main import main


def invoke(paths, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--home", str(paths.root), *args])
    except SystemExit as exc:
        code = int(exc.code) if exc.code is not None else 0
    return code, out.getvalue(), err.getvalue()


def write_map(paths, repo: Path) -> None:
    (paths.root / ".works").mkdir(exist_ok=True)
    (paths.root / ".works" / "products.yaml").write_text(
        f"products:\n  firefox:\n    repo: {repo.as_posix()}\n", encoding="utf-8"
    )


def test_source_github_queues_issues_for_the_mapped_repo(paths, tmp_path, monkeypatch) -> None:
    repo = tmp_path / "firefox"
    repo.mkdir()
    write_map(paths, repo)
    monkeypatch.setattr(
        "works.application.intake.sources.github_issues",
        lambda *a, **k: [Issue(ref="owner/name#1", title="Crash on start")],
    )

    code, out, err = invoke(
        paths, "source", "github", "owner/name", "--product", "firefox", "--json"
    )

    assert code == 0, err
    body = json.loads(out.strip().splitlines()[-1])
    assert body["found"] == 1
    assert body["created"] == 1
    task = Queue(paths).load(body["tasks"][0])
    assert task.repo == str(repo.resolve())
    assert task.source.kind.value == "tracker"


def test_source_github_is_idempotent(paths, tmp_path, monkeypatch) -> None:
    repo = tmp_path / "firefox"
    repo.mkdir()
    write_map(paths, repo)
    monkeypatch.setattr(
        "works.application.intake.sources.github_issues",
        lambda *a, **k: [Issue(ref="owner/name#1", title="Crash on start")],
    )

    first = invoke(paths, "source", "github", "owner/name", "--product", "firefox", "--json")
    second = invoke(paths, "source", "github", "owner/name", "--product", "firefox", "--json")

    assert first[0] == 0
    assert json.loads(first[1].strip().splitlines()[-1])["created"] == 1
    assert json.loads(second[1].strip().splitlines()[-1])["created"] == 0


def test_source_refuses_an_unmapped_product(paths, monkeypatch) -> None:
    (paths.root / ".works").mkdir()
    (paths.root / ".works" / "products.yaml").write_text(
        "products:\n  blender:\n    repo: apps/blender\n", encoding="utf-8"
    )
    monkeypatch.setattr("works.application.intake.sources.github_issues", lambda *a, **k: [])

    code, _, err = invoke(paths, "source", "github", "owner/name", "--product", "firefox")

    assert code != 0
    assert "known products: blender" in err


def test_source_detector_queues_firing_alerts(paths, tmp_path) -> None:
    repo = tmp_path / "firefox"
    repo.mkdir()
    write_map(paths, repo)
    alerts = tmp_path / "alerts.json"
    alerts.write_text(
        json.dumps(
            [
                {"id": "a1", "title": "Disk full", "severity": "critical"},
                {"status": "resolved", "id": "a2", "title": "Recovered"},
            ]
        ),
        encoding="utf-8",
    )

    code, out, err = invoke(
        paths,
        "source",
        "detector",
        "--file",
        str(alerts),
        "--product",
        "firefox",
        "--json",
    )

    assert code == 0, err
    body = json.loads(out.strip().splitlines()[-1])
    assert body["found"] == 1
    assert body["created"] == 1


def test_source_jira_requires_credentials(paths, monkeypatch) -> None:
    repo = paths.root / "repo"
    repo.mkdir()
    write_map(paths, repo)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_TOKEN", raising=False)

    code, _, err = invoke(
        paths,
        "source",
        "jira",
        "--url",
        "https://jira.example",
        "--jql",
        "project = X",
        "--product",
        "firefox",
    )

    assert code != 0
    assert "JIRA_EMAIL" in err


def test_swarm_doctor_reports_a_blocked_checkout(paths, monkeypatch) -> None:
    from works.adapters.harness.swarm.harness import SwarmDiagnostic

    monkeypatch.setattr(
        "works.adapters.harness.swarm.harness.preflight",
        lambda *a, **k: SwarmDiagnostic(False, "missing agent_gateway", ("python",), 1, "boom"),
    )

    code, out, _ = invoke(paths, "swarm", "doctor", "--json")

    assert code == 8
    body = json.loads(out.strip().splitlines()[-1])
    assert body["ok"] is False
    assert body["contract"] == "works.swarm.v1"
    assert body["output_tail"] == "boom"


@pytest.mark.parametrize("value", ["not json", '["ok", 1]'])
def test_the_swarm_entrypoint_must_be_a_json_string_array(monkeypatch, value: str) -> None:
    from works.adapters.harness.swarm.harness import default_entrypoint
    from works.domain.errors import ConfigError

    monkeypatch.setenv("WORKS_SWARM_ENTRYPOINT", value)

    with pytest.raises(ConfigError):
        default_entrypoint()
