from __future__ import annotations

from works.runner import SubprocessRunner, sanitize_env


def test_env_drops_credentials() -> None:
    clean = sanitize_env(
        {
            "PATH": "/bin",
            "OPENAI_API_KEY": "secret",
            "GITHUB_TOKEN": "secret",
            "DB_PASSWORD": "secret",
            "AWS_CREDENTIALS": "secret",
            "MONKEY": "also dropped because KEY is in the name",
            "WORKS_BUILDER_API_KEY": "dropped: the verifier never inherits the builder key",
            "WORKS_VERIFIER_API_KEY": "dropped: even the verifier key needs an explicit env",
            "HOME": "/home/me",
        }
    )
    assert "OPENAI_API_KEY" not in clean
    assert "GITHUB_TOKEN" not in clean
    assert "DB_PASSWORD" not in clean
    assert "AWS_CREDENTIALS" not in clean
    assert "MONKEY" not in clean
    assert "WORKS_BUILDER_API_KEY" not in clean
    assert "WORKS_VERIFIER_API_KEY" not in clean
    assert clean["PATH"] == "/bin"
    assert clean["HOME"] == "/home/me"


def test_allow_list_keeps_a_credential_when_explicit() -> None:
    clean = sanitize_env({"MY_TOKEN": "x"}, allow=("MY_TOKEN",))
    assert clean["MY_TOKEN"] == "x"  # noqa: S105 - the value is a placeholder


def test_run_captures_output(tmp_path) -> None:
    runner = SubprocessRunner()
    result = runner.run(
        ["python", "-c", "import sys; print('out'); print('err', file=sys.stderr)"],
        tmp_path,
    )
    assert result.ok
    assert "out" in result.stdout
    assert "err" in result.stderr
    assert result.exit_code == 0
    assert len(result.output_sha256) == 64
    record = result.record("demo")
    assert record.step == "demo"
    assert record.argv[0] == "python"


def test_a_failing_command_is_not_ok(tmp_path) -> None:
    result = SubprocessRunner().run(["python", "-c", "raise SystemExit(3)"], tmp_path)
    assert not result.ok
    assert result.exit_code == 3


def test_bytecode_writing_is_disabled(tmp_path) -> None:
    result = SubprocessRunner().run(
        ["python", "-c", "import os; print(os.environ['PYTHONDONTWRITEBYTECODE'])"],
        tmp_path,
    )
    assert result.ok
    assert result.stdout.strip() == "1"


def test_timeout_kills_the_process(tmp_path) -> None:
    result = SubprocessRunner().run(
        ["python", "-c", "import time; time.sleep(30)"], tmp_path, timeout_s=1
    )
    assert result.timed_out
    assert not result.ok
    assert result.exit_code != 0
