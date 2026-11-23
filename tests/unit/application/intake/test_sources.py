from __future__ import annotations

import base64
import io
import urllib.error
import urllib.request
from typing import Any

import pytest

from works.adapters.queue.store import Queue
from works.application.intake.sources import _urllib_get, github_issues, ingest_issues, jira_issues
from works.domain.errors import ConfigError


def fake_transport(status: int, payload: Any):
    calls: list[tuple[str, dict[str, str]]] = []

    def transport(url: str, headers: dict[str, str]) -> tuple[int, Any]:
        calls.append((url, headers))
        return status, payload

    transport.calls = calls  # type: ignore[attr-defined]
    return transport


def test_github_reads_open_issues_and_skips_pull_requests() -> None:
    transport = fake_transport(
        200,
        [
            {"number": 7, "title": "  Calculator subtracts  ", "body": "steps"},
            {"number": 8, "title": "A pull request", "pull_request": {"url": "x"}},
            {"number": 9, "title": "   "},
            {"title": "no number"},
            "not an object",
        ],
    )

    issues = github_issues(
        "owner/name",
        label="bug",
        token="secret",  # noqa: S106
        transport=transport,
    )

    assert [(issue.ref, issue.title, issue.body) for issue in issues] == [
        ("owner/name#7", "Calculator subtracts", "steps")
    ]
    url, headers = transport.calls[0]  # type: ignore[attr-defined]
    assert "labels=bug" in url
    assert "state=open" in url
    assert headers["Authorization"] == "Bearer secret"


def test_github_refuses_a_non_200_response() -> None:
    transport = fake_transport(403, {"message": "rate limited"})

    with pytest.raises(ConfigError, match="GitHub refused"):
        github_issues("owner/name", transport=transport)


def test_jira_needs_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_TOKEN", raising=False)

    with pytest.raises(ConfigError, match="JIRA_EMAIL"):
        jira_issues("https://jira.example", "project = X", transport=fake_transport(200, {}))


def test_jira_reads_issues_with_basic_auth() -> None:
    transport = fake_transport(
        200,
        {
            "issues": [
                {"key": "FIRE-3", "fields": {"summary": "Crash on start"}},
                {"key": "FIRE-4", "fields": {}},
                {"fields": {"summary": "no key"}},
            ]
        },
    )

    issues = jira_issues(
        "https://jira.example/",
        "project = FIRE",
        email="me@example.com",
        token="token",  # noqa: S106
        transport=transport,
    )

    assert [(issue.ref, issue.title) for issue in issues] == [("FIRE-3", "Crash on start")]
    url, headers = transport.calls[0]  # type: ignore[attr-defined]
    expected = base64.b64encode(b"me@example.com:token").decode()
    assert headers["Authorization"] == f"Basic {expected}"
    assert "project%20%3D%20FIRE" in url


def test_jira_refuses_a_non_200_response() -> None:
    transport = fake_transport(401, {"errorMessages": ["bad token"]})

    with pytest.raises(ConfigError, match="Jira refused"):
        jira_issues(
            "https://jira.example",
            "project = X",
            email="me@example.com",
            token="token",  # noqa: S106
            transport=transport,
        )


def test_urllib_transport_reads_json_and_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status = 200

        def read(self) -> bytes:
            return b'{"ok": true}'

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Response())
    assert _urllib_get("https://example.test", {}) == (200, {"ok": True})

    def refuse(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError(
            "https://example.test",
            403,
            "forbidden",
            hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"message": "no"}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    assert _urllib_get("https://example.test", {}) == (403, {"message": "no"})


def test_ingesting_the_same_issue_twice_returns_one_task(paths) -> None:
    transport = fake_transport(
        200,
        [
            {"number": 1, "title": "First"},
            {"number": 2, "title": "Second"},
        ],
    )

    first = ingest_issues(
        Queue(paths),
        product="firefox",
        repo=str(paths.root / "firefox"),
        issues=github_issues("owner/name", transport=transport),
    )
    second = ingest_issues(
        Queue(paths),
        product="firefox",
        repo=str(paths.root / "firefox"),
        issues=github_issues("owner/name", transport=transport),
    )

    assert [created for _, created in first] == [True, True]
    assert [created for _, created in second] == [False, False]
    assert [task.id for task, _ in first] == [task.id for task, _ in second]
