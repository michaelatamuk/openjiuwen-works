from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout

import pytest

from tests.test_deliver import _released, _remote
from works.cli import main
from works.deliver import deliver
from works.deploy import Deployment, deploy
from works.errors import ConfigError
from works.queue import Queue


def _delivered(paths, repo, tmp_path):
    task, _, _ = _released(paths, repo)
    _remote(tmp_path, repo)
    delivery = deliver(paths, task.id)
    return task, delivery


def test_deploy_runs_the_command_after_delivery(paths, repo, tmp_path) -> None:
    task, delivery = _delivered(paths, repo, tmp_path)

    result = deploy(
        paths,
        task.id,
        command=[sys.executable, "-c", "print('deployed')"],
        environment="staging",
    )

    assert result.status == "deployed"
    assert result.commit == delivery.commit
    assert result.environment == "staging"
    assert result.exit_code == 0
    assert "deployed" in result.output_tail
    assert (paths.runs / delivery.run_id / "deployment.json").exists()
    events = [e for e in Queue(paths).events(task.id) if e.type == "deploy.finished"]
    assert len(events) == 1
    assert events[0].data["commit"] == delivery.commit


def test_deploy_is_idempotent_and_force_repeats(paths, repo, tmp_path) -> None:
    task, _ = _delivered(paths, repo, tmp_path)
    command = [sys.executable, "-c", "print('once')"]

    first = deploy(paths, task.id, command=command)
    second = deploy(paths, task.id, command=command)
    forced = deploy(paths, task.id, command=command, force=True)

    assert first.created is True
    assert second.created is False
    assert second.status == "deployed"
    assert forced.created is True


def test_a_dry_run_does_not_execute_the_command(paths, repo, tmp_path) -> None:
    task, _ = _delivered(paths, repo, tmp_path)

    result = deploy(
        paths,
        task.id,
        command=[sys.executable, "-c", "raise SystemExit(9)"],
        dry_run=True,
    )

    assert result.status == "dry_run"
    assert result.exit_code == 0
    assert result.dry_run is True
    assert "dry run" in result.notes[0]


def test_a_failed_command_is_recorded_as_failed(paths, repo, tmp_path) -> None:
    task, _ = _delivered(paths, repo, tmp_path)

    result = deploy(paths, task.id, command=[sys.executable, "-c", "raise SystemExit(4)"])

    assert result.status == "failed"
    assert result.exit_code == 4
    events = [e for e in Queue(paths).events(task.id) if e.type == "deploy.finished"]
    assert events[-1].data["status"] == "failed"


def test_deploy_requires_delivery(paths, repo) -> None:
    task, _, _ = _released(paths, repo)

    with pytest.raises(ConfigError, match="has not been delivered"):
        deploy(paths, task.id, command=[sys.executable, "-c", "print('x')"])


def test_deploy_reads_the_product_map(paths, repo, tmp_path) -> None:
    task, _ = _delivered(paths, repo, tmp_path)
    config = paths.root / ".works"
    config.mkdir()
    (config / "products.yaml").write_text(
        "products:\n  openjiuwen:\n    repo: .\n    deploy: ['python', '-c', 'print(1)']\n",
        encoding="utf-8",
    )

    result = deploy(paths, task.id)

    assert result.command == ["python", "-c", "print(1)"]


def test_deploy_without_a_command_is_a_config_error(paths, repo, tmp_path) -> None:
    task, _ = _delivered(paths, repo, tmp_path)

    with pytest.raises(ConfigError, match="no deploy command"):
        deploy(paths, task.id)


def test_the_cli_deploys_and_exits_zero(paths, repo, tmp_path) -> None:
    task, _ = _delivered(paths, repo, tmp_path)
    out, err = io.StringIO(), io.StringIO()
    command = json.dumps([sys.executable, "-c", "print('ok')"])

    with redirect_stdout(out), redirect_stderr(err):
        code = main(
            ["--home", str(paths.root), "deploy", task.id, "--command", command, "--json"]
        )

    assert code == 0, err.getvalue()
    body = json.loads(out.getvalue().strip().splitlines()[-1])
    assert body["status"] == "deployed"


def test_the_cli_exits_blocked_on_a_failed_deploy(paths, repo, tmp_path) -> None:
    task, _ = _delivered(paths, repo, tmp_path)
    out, err = io.StringIO(), io.StringIO()
    command = json.dumps([sys.executable, "-c", "raise SystemExit(2)"])

    with redirect_stdout(out), redirect_stderr(err):
        code = main(["--home", str(paths.root), "deploy", task.id, "--command", command])

    assert code == 8
    assert "failed" in out.getvalue()


def test_deployment_round_trips_through_json() -> None:
    deployment = Deployment(
        task_id="t-1",
        run_id="r-1",
        commit="abc",
        command=["true"],
        status="deployed",
    )

    assert Deployment.model_validate_json(deployment.model_dump_json()).as_dict()["commit"] == "abc"
